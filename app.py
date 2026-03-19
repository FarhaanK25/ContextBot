import hashlib
import sqlite3
import chromadb
from sentence_transformers import SentenceTransformer
import gradio as gr
from PyPDF2 import PdfReader
from concurrent.futures import ProcessPoolExecutor 
from datetime import datetime
import pandas as pd
from concurrent.futures import as_completed
import time

# Configuration 
DB_PATH = "ingest_registry.db"
CHROMA_PATH = ".chromadb"
COLLECTION_NAME = "Books"
MODEL_NAME = 'all-MiniLM-L6-v2'

# Singleton SQLite Connection 
class SQLiteSingleton:
    _connection = None

    @classmethod
    def get_connection(cls):
        if cls._connection is None:
            cls._connection = sqlite3.connect(DB_PATH, check_same_thread=False)
        return cls._connection

    @classmethod
    def close_connection(cls):
        if cls._connection:
            cls._connection.close()
            cls._connection = None

import atexit
atexit.register(SQLiteSingleton.close_connection)

# Initialize ChromaDB client and collection 
client = chromadb.PersistentClient(path=CHROMA_PATH)
collection = client.get_or_create_collection(name=COLLECTION_NAME)

# Initialize embedding model and Groq client 
model = SentenceTransformer(MODEL_NAME)

# Set up SQLite registry (create table only once) 
def init_registry(db_path: str):
    conn = SQLiteSingleton.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            book_hash TEXT UNIQUE NOT NULL,
            filename TEXT NOT NULL,
            upload_time TEXT NOT NULL,
            file_size INTEGER NOT NULL,
            num_chunks INTEGER NOT NULL
        )
        '''
    )
    conn.commit()

# Initialize registry on startup
init_registry(DB_PATH)

# Chunk and ingest logic with metadata 
def ingest(content: str, title: str, filename: str, book_hash: str, upload_time: str, chunk_size: int = 200, overlap: int = 50) -> int:
    words = content.split()
    total_words = len(words)
    start = 0

    ids = []
    documents = []
    metadatas = []

    while start < total_words:
        end = min(start + chunk_size, total_words)
        chunk_text = " ".join(words[start:end])
        cid = hashlib.sha256((title + chunk_text).encode('utf-8')).hexdigest()

        metadata = {
            'book_title': title,
            'book_hash': book_hash,
            'filename': filename,
            'upload_timestamp': upload_time
        }

        ids.append(cid)
        documents.append(chunk_text)
        metadatas.append(metadata)

        start += (chunk_size - overlap)

    # Generate embeddings in batch using SentenceTransformer 
    embeddings = model.encode(documents, batch_size=32, show_progress_bar=False)

    # Add to ChromaDB with precomputed embeddings
    collection.add(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings)

    return len(ids)

# Process a single book file
def process_book_path(book_path: str) -> str:
    import os
    import hashlib
    import sqlite3
    import chromadb
    from sentence_transformers import SentenceTransformer
    from PyPDF2 import PdfReader
    from datetime import datetime

    # Configuration
    DB_PATH = "ingest_registry.db"
    CHROMA_PATH = ".chromadb"
    COLLECTION_NAME = "Books"

    # Initialize per-process instances
    collection = client.get_or_create_collection(name=COLLECTION_NAME)

    ext = os.path.splitext(book_path)[1].lower()
    filename = os.path.basename(book_path)
    title = os.path.splitext(filename)[0]

    with open(book_path, "rb") as f:
        file_bytes = f.read()
        book_hash = hashlib.sha256(file_bytes).hexdigest()

    # Check for duplicates
    conn = SQLiteSingleton.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM books WHERE book_hash = ?", (book_hash,))
    result = cursor.fetchone()
    if result:
        return f"Book **{title}** already ingested. Skipping duplicate."

    try:
        # Read content
        if ext == ".pdf":
            reader = PdfReader(book_path)  # Fixed: use file path directly
            pages = [page.extract_text() or "" for page in reader.pages]
            content = "\n".join(pages)
        elif ext == ".txt":
            with open(book_path, "r", encoding="utf-8") as f:
                content = f.read()
        else:
            return f"Unsupported file type: {filename}"

        # Metadata
        upload_time = datetime.utcnow().isoformat()
        file_size = os.path.getsize(book_path) / 1000  # in KB

        # Chunking and ingestion
        num_chunks = ingest(content, title, filename, book_hash, upload_time, chunk_size=300, overlap=20)

        # Register in registry
        cursor.execute(
            '''
            INSERT INTO books
            (title, book_hash, filename, upload_time, file_size, num_chunks)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            (title, book_hash, filename, upload_time, file_size, num_chunks)
        )
        conn.commit()

        return f"Uploaded {num_chunks} chunks from **{title}**"

    except Exception as e:
        return f"Error processing {filename}: {str(e)}"


# --- Ingest multiple books using ProcessPoolExecutor ---
def upload_and_ingest(book_files):
    if not book_files:
        yield "No files uploaded."
        return

    file_paths = [f.name for f in book_files]
    status_log = ""

    with ProcessPoolExecutor() as executor:
        futures = [executor.submit(process_book_path, path) for path in file_paths]
        for future in as_completed(futures):
            result = future.result()
            status_log += result + "\n"
            yield status_log.strip()

def get_ingested_filenames():
    conn = SQLiteSingleton.get_connection()
    df = pd.read_sql_query("SELECT filename FROM books", conn)
    return gr.Dropdown(choices = df["filename"].tolist())

def delete_book(selected_filename):
    try:
        if not selected_filename:
            return "Please select a book to delete."

        # Fetch the book_hash for the selected filename
        conn = SQLiteSingleton.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT book_hash FROM books WHERE filename = ?", (selected_filename,))
        result = cursor.fetchone()
        if not result:
            return f"Book '{selected_filename}' not found in registry."
        book_hash = result[0]

        # Delete from ChromaDB by filtering based on book_hash in metadata
        results = collection.get(where={"book_hash": book_hash})
        if results and 'ids' in results:
            ids_to_delete = results['ids']
            if ids_to_delete:
                collection.delete(ids=ids_to_delete)

        # Delete from SQLite
        conn = SQLiteSingleton.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM books WHERE book_hash = ?", (book_hash,))
        conn.commit()

        return f"🗑️ Successfully deleted book '{selected_filename}'."

    except Exception as e:
        return f"Error deleting book '{selected_filename}': {str(e)}"

import requests
import json 
import time 

from sentence_transformers import CrossEncoder

cross_encoder = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')

def rerank(query: str, docs: list[str], top_k: int = 10) -> list[str]:
    pairs = [[query, doc] for doc in docs]
    scores = cross_encoder.predict(pairs)
    ranked = sorted(zip(docs, scores), key=lambda x: x[1], reverse=True)
    return [doc for doc, _ in ranked[:top_k]]

# RAG generation logic 
import os
from groq import Groq

groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

def generate_answer(query: str, history):
    # Retrieve
    q_emb = model.encode(query).tolist()
    results = collection.query(query_embeddings=[q_emb], n_results=10)
    docs = results.get('documents', [[]])[0]

    # Re-rank retrieved docs
    docs = rerank(query, docs, top_k=10)
    context = '\n\n'.join(docs)

    # Construct Prompts
    prompt = (
        f"Use the context below to answer the given question."
        f"\n\nContext:\n{context}\n\nQuestion: {query}\nAnswer:"
    )

    system_prompt = (
        "Do NOT reveal the context. "
        "Do NOT mention that the answer is based on the Context. "
        "If the question is not related to the context, reply: 'Sorry, I don't know the answer to that question.'"
    )

    try:
        # Streamed request to Groq API
        stream = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            # You can change this to "gemma2-9b-it" if you want to stick with Gemma
            model="llama-3.3-70b-versatile", 
            stream=True,
        )

        for chunk in stream:
            # Groq returns chunks where the content might be empty on the first/last yield
            delta = chunk.choices[0].delta.content
            if delta is not None:
                print(delta, end="", flush=True)
                yield delta  # Streaming token-by-token to Gradio

    except Exception as e:
        yield f"\n\nError communicating with API: {str(e)}"

def stream_wrapper(message, history):
    history = history or []
    generator = generate_answer(message, history)
    response = ""
    for chunk in generator:
        response += chunk
        # Return both updated history and "" to clear the textbox
        yield (
            history + [
                {"role": "user", "content": message},
                {"role": "assistant", "content": response}
            ],
            ""
        )
        time.sleep(0.015)

# Gradio UI
with gr.Blocks() as demo:
    gr.Markdown("# Context Bot")
    with gr.Row():
        with gr.Column(scale=1):
            upload = gr.File(label="Upload Books (PDF or TXT)", file_types=[".pdf", ".txt"], file_count="multiple")
            ingest_btn = gr.Button("Ingest Books")
            status = gr.Textbox(label="Ingestion Status", interactive=False, lines=6)
        with gr.Column(scale=1):
            view_btn=gr.Button("View Books")
            delete_dropdown = gr.Dropdown(label="Select Book to Delete", interactive=True, choices=[])
            delete_btn = gr.Button("Delete Selected Book")
            delete_status = gr.Textbox(label="Deletion Status", interactive=False)
        with gr.Column(scale=3):
            chatbot = gr.Chatbot(label="Chat")
            query = gr.Textbox(label="Ask a question")
            query.submit(stream_wrapper, inputs=[query, chatbot], outputs=[chatbot, query]  # return to both chatbot and query box
)

    ingest_btn.click(fn=upload_and_ingest, inputs=upload, outputs=status, show_progress=True)
    view_btn.click(fn=get_ingested_filenames, outputs=delete_dropdown)
    delete_btn.click(fn=delete_book, inputs=delete_dropdown, outputs=delete_status)

if __name__ == '__main__':
    demo.queue()  # Enable Gradio's built-in queuing system for better concurrency handling
    demo.launch()
