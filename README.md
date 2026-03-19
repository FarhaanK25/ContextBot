---
title: ContextBot
emoji: 📚
colorFrom: blue
colorTo: purple
sdk: gradio
app_file: app.py
pinned: false
---
# ContextBot: Advanced RAG Chatbot

An optimized, full-featured Retrieval-Augmented Generation (RAG) application that allows you to chat with your personal documents. Built with a Gradio frontend, it features concurrent document processing, SQLite-backed file management, two-stage document retrieval, and lightning-fast LLM inference via the Groq API.

## Features

* **Multi-Format Document Ingestion:** Upload multiple `.pdf` or `.txt` files at once.
* **Concurrent Processing:** Utilizes multiprocessing to chunk, embed, and ingest multiple large documents in parallel.
* **Smart Deduplication:** Calculates SHA-256 hashes of uploaded files to automatically prevent duplicate ingestions.
* **Two-Stage Retrieval:**
  * **Stage 1 (Bi-Encoder):** Uses `all-MiniLM-L6-v2` for fast, initial semantic search using ChromaDB.
  * **Stage 2 (Cross-Encoder):** Uses `ms-marco-MiniLM-L-6-v2` to re-rank the retrieved chunks for maximum contextual relevance.
* **Document Management:** View all ingested files and securely delete specific documents from both the SQLite registry and the ChromaDB vector store.
* **Real-Time Streaming:** Enjoy a typewriter-like chat experience with token-by-token streaming from the Groq API.

## Tech Stack

* **Frontend UI:** [Gradio](https://gradio.app/)
* **Vector Database:** [ChromaDB](https://www.trychroma.com/) (Persistent Local Storage)
* **Metadata Registry:** SQLite
* **Embeddings & Re-ranking:** `sentence-transformers`
* **LLM Inference:** [Groq API](https://groq.com/)
* **PDF Parsing:** `PyPDF2`

## Installation & Setup

### 1. Clone the Repository
```bash
git clone [https://github.com/FarhaanK25/ContextBot.git](https://github.com/FarhaanK25/ContextBot.git)
cd ContextBot
```

### 2. Create a Virtual Environment (Recommended)
```bash
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Mac/Linux:
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Set Up Your Environment Variables
Create a file named .env in the root directory of the project and add your Groq API key:
```bash
GROQ_API_KEY=your_actual_groq_api_key_here
```

### 5. Run the Application
```bash
python app.py
```
The Gradio interface will automatically launch in your default web browser.

## How to Use
### 1. Upload Data: 
Go to the "Upload Books" section, select your PDFs or TXT files, and click Ingest Books. Wait for the status box to confirm successful chunking and ingestion.
### 2. Chat: 
Type your questions into the chatbox. The bot will retrieve the most relevant sections from your uploaded documents and stream an answer.
### 3. Manage Data: 
Use the "View Books" button to refresh the list of ingested files. Select a file from the dropdown and click "Delete Selected Book" to completely remove its data from the system.

## Project Structure
* **app.py**: The main application code containing the RAG pipeline, database management, and UI logic.
* **requirements.txt**: List of Python dependencies.
* **.chromadb/**: (Generated automatically) Local storage folder for the vector database.
* **ingest_registry.db**: (Generated automatically) SQLite database tracking document metadata and hashes.

## License
This project is open-source and available under the MIT License.
