# Medical Advisor AI

**A secure, local-first macOS application for exploring and analyzing your personal health records with the power of Large Language Models (LLMs).**

This application allows you to import your health data from standard Clinical Document Architecture (CDA) XML files (like those exported from MyChart), store it in a private, on-device database, and use an AI-powered chat interface to ask questions about your health history in plain English.

**Disclaimer:** ⚠️ This is a proof-of-concept application and is **NOT a medical device**. It is intended for educational and informational purposes only. Do not use it for self-diagnosis or as a substitute for professional medical advice, diagnosis, or treatment. Always seek the advice of your physician or other qualified health provider with any questions you may have regarding a medical condition.

---

## Features

-   **Secure Data Import:** Import your health records from one or more CDA XML files. All data processing happens locally on your Mac.
-   **Private, On-Device Storage:** Your health information is parsed and stored in a local SQLite database file that you control. No medical data is ever sent to a remote server, except for the anonymized, relevant context you explicitly approve to be sent to the AI service.
-   **Comprehensive Record Browser:** A searchable, categorized interface to view all your imported medical data, including problems, medications, allergies, lab results, procedures, and more.
-   **Flexible AI Integration:** Choose between two powerful AI services:
    -   **Google Gemini:** A high-performance, cloud-based model (requires an API key).
    -   **Ollama:** Run a variety of open-source models (like Llama 3, Gemma 2, etc.) entirely on your own machine for maximum privacy.
-   **Intelligent Context Retrieval:** The AI doesn't just perform a simple search. It analyzes your symptoms, determines which categories of your medical history are relevant, and retrieves only that specific data to form a context for its analysis.
-   **User Confirmation Step:** Before any data is sent to the AI for final analysis, you are shown a summary of the retrieved information and must confirm its use.
-   **Secure API Key Storage:** Your Google Gemini API key is stored securely in the macOS Keychain, not in plain text.

## How It Works

The application is designed with a modular, privacy-first architecture. The process flows through three main stages:

### 1. Import (`ImporterView`)

1.  **File Selection:** You select one or more CDA XML files containing your health records.
2.  **Destination:** You choose a location on your Mac to save the new `MyHealthData.db` SQLite database file.
3.  **Parsing:** The `CDAXMLParser` reads each XML file, navigating the complex structure to extract individual records (patient info, allergies, medications, etc.).
4.  **Database Creation:** The `DatabaseManager`, powered by **GRDB.swift**, creates the SQLite database and inserts the parsed records into the appropriate tables, preventing duplicate entries.

### 2. Browse (`RecordsView`)

1.  **Data Fetching:** The `RecordsViewModel` uses the `DatabaseManager` to fetch all records from the SQLite database.
2.  **Display:** The data is presented in a clean, searchable, master-detail interface, with categories in a sidebar for easy navigation.

### 3. Advise (`AdvisorView`)

This is the core AI-powered workflow:

1.  **Symptom Input:** You describe your current symptoms in the chat box.
2.  **Category Identification:** The `AdvisorViewModel` sends your symptoms and the database schema to the selected AI service (`GeminiService` or `OllamaService`). The AI returns a list of relevant medical categories (e.g., "Current Medications," "Recent Lab Results for Cholesterol").
3.  **Query Generation:** The view model then asks the AI to generate specific SQLite queries to retrieve data for only those categories. The AI is instructed to be highly specific and not use broad `SELECT *` queries.
4.  **Local Data Retrieval:** The `DatabaseManager` executes these queries on your local database.
5.  **Summarization & Confirmation:** The raw query results are sent back to the AI, which summarizes the information (especially long clinical notes) into a concise format. This summarized data is then presented to you for confirmation.
6.  **Final Analysis:** Once you confirm, your original symptoms and the summarized, confirmed medical context are sent to the AI one last time. The AI performs its final analysis and provides a structured, helpful response in the chat.

## Setup and Installation

### Prerequisites

-   macOS 14.0+
-   Xcode 15.0+
-   A copy of your medical records in CDA XML format (e.g., from a MyChart export).

### 1. Clone the Repository

```bash
git clone https://github.com/kyunghyuncho/MyChartExplorer.git
cd medical-advisor-ai
```

### 2. Choose Your AI Service

You can use either Gemini (cloud) or Ollama (local).

**For Google Gemini (Recommended for best performance):**

1.  Go to [Google AI Studio](https://aistudio.google.com/).
2.  Create a new API key.
3.  Launch the app. On the "Advisor" tab, you will be prompted to enter your API key. It will be saved securely in your macOS Keychain.

**For Ollama (Recommended for best privacy):**

1.  Download and install [Ollama](https://ollama.com/) for macOS.
2.  Pull a model from the command line. A powerful but relatively lightweight model is recommended:
    ```bash
    ollama pull gemma3:4b-it-qat
    ```
3.  Launch the app and select "Ollama (Local)" from the picker in the toolbar. The app is pre-configured to connect to Ollama running on `http://localhost:11434`.

### 3. Build and Run

Open the project in Xcode and press `Cmd+R` to build and run the application.

## Usage Guide

1.  **Importer Tab:**
    -   Click "Add Files" to select your XML health records.
    -   Click "Set..." to choose where to save your database file.
    -   Click "Start Import". The log on the right will show the progress.
2.  **Records Tab:**
    -   Once the import is complete, go to the "Records" tab.
    -   Use the sidebar to navigate between different categories of your health data.
    -   Use the search bar to filter across all your records.
3.  **Advisor Tab:**
    -   Select your desired AI service (Gemini or Ollama) from the toolbar.
    -   If using Gemini, enter your API key when prompted.
    -   Type your symptoms into the chat box and press Enter.
    -   Wait for the AI to process and retrieve relevant data.
    -   A panel will appear on the right showing the data to be used. Review it and click "Confirm and Advise" to proceed, or "Cancel".
    -   Read the AI's final analysis in the chat window.

## License

This project is licensed under the MIT License. See the [LICENSE](https://www.google.com/search?q=LICENSE) file for details.
