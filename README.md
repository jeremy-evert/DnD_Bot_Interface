# DnD_Bot_Interface
Building a backend that will let me play dungeons and dragons with a chatbot and have the documents to make everything work.


## Every Time Activate the Virtual Environment
```source DND/bin/activate```

note: if its not made yet, you can make it like this:
```python -m venv DND```

Activate the virtual environment:
On Windows:
```DND\Scripts\activate```

On macOS/Linux:
```source DND/bin/activate```
---

# To-Do List for DnD GUI with Llama LLM Backend

| **Item #** | **Task**                                                                 | **Assigned To** | **Dependencies**               |
|------------|-----------------------------------------------------------------------|-----------------|-------------------------------|
| 1          | Set up the Python environment and install dependencies (PyQt, Llama LLM, TTS libraries) | JE              | None                          |
| 2          | Design the GUI layout with placeholders for personas, characters, and table | JE              | None                          |
| 3          | Integrate Llama LLM for basic natural language understanding and response generation | JE              | 1, 2                         |
| 4          | Create data models for players, characters, and the Dungeon Master (DM) | JE              | 1, 2                         |
| 5          | Implement digital character sheets with traditional DnD stats (Strength, Dexterity, etc.) | JE              | 4                            |
| 6          | Develop tools for the Dungeon Master to manage the arena and NPC interactions | JE              | 3, 4, 5                      |
| 7          | Add functionality to represent characters as figurines on the virtual tabletop | JE              | 2, 4                         |
| 8          | Implement voice recording functionality for personal personas           | JE              | 1, 2                         |
| 9          | Build a feature for uploading recorded voices to train personal persona speech synthesis | JE              | 8                            |
| 10         | Train AI models to generate custom voices for personal personas based on uploaded samples | JE              | 9                            |
| 11         | Select or generate default voices for character personas (e.g., Vincent Price-style voice for Dragonborn) | JE              | 7, 9                         |
| 12         | Integrate text-to-speech (TTS) for personal and character personas       | JE              | 10, 11                       |
| 13         | Add real-time speech recognition to allow players to interact using their voice | JE              | 12                           |
| 14         | Enable seamless switching between personal and character voices based on context | JE              | 12, 13                       |
| 15         | Implement health and stats tracking for all characters and NPCs          | JE              | 5, 6                         |
| 16         | Finalize DM tools for real-time scenario updates                         | JE              | 6, 15                        |
| 17         | Test local play functionality, ensuring smooth voice integration         | JE              | 14, 16                       |
| 18         | Document the setup and usage of the application                          | JE              | 17                           |

---

### **Sub To-Do List for Item 1: Set up the project environment and initialize the repository**

| **Item #** | **Task Description**                                                                                               | **Assigned To**       | **Status** | **Dependencies**                                                                                                   |
|------------|-------------------------------------------------------------------------------------------------------------------|-----------------------|------------|-------------------------------------------------------------------------------------------------------------------|
| 1.1        | Install Python (version 3.9 or later)                                                                             | JE                    | [ ]        | None                                                                                                              |
| 1.2        | Install Git for version control                                                                                   | JE                    | [ ]        | None                                                                                                              |
| 1.3        | Create a new GitHub repository                                                                                   | JE                    | [ ]        | 1.2                                                                                                               |
| 1.4        | Clone the GitHub repository locally                                                                              | JE                    | [ ]        | 1.3                                                                                                               |
| 1.5        | Set up a virtual environment using `venv`                                                                        | JE                    | [ ]        | 1.1                                                                                                               |
| 1.6        | Install core dependencies (PyTorch, PyQt5, etc.)                                                                 | JE                    | [ ]        | 1.5                                                                                                               |
| 1.7        | Initialize the project directory structure                                                                       | JE                    | [ ]        | 1.4                                                                                                               |
| 1.8        | Configure `requirements.txt` to save dependencies                                                                | JE                    | [ ]        | 1.6                                                                                                               |
| 1.9        | Create a README.md file to describe the project                                                                  | JE                    | [ ]        | None                                                                                                              |
| 1.10       | Add a `.gitignore` file to exclude unnecessary files                                                             | JE                    | [ ]        | 1.4                                                                                                               |
| 1.11       | Test initial setup with a basic script                                                                           | JE                    | [ ]        | 1.7                                                                                                               |
| 1.12       | Commit and push changes to the GitHub repository                                                                 | JE                    | [ ]        | 1.11                                                                                                              |
| 1.13       | Document issues or questions by creating a section for tracking tasks or challenges on GitHub                    | JE                    | [ ]        | None                                                                                                              |

---

### Key Notes:
1. **Voice Recording and Uploading**: Ensure that the system supports easy recording and uploading of audio samples to train personal persona voices. The process should be user-friendly and locally stored to maintain privacy.
2. **Voice Synthesis**: Research and integrate open-source TTS models (e.g., Coqui TTS or similar) to provide high-quality custom voice outputs.
3. **Speech Recognition**: Use a local speech recognition library like Vosk for privacy and low-latency processing.
4. **Testing and Refinement**: Each voice-related feature should be rigorously tested to ensure natural transitions between personal and character personas during gameplay.


---

## 📝 How to Contribute
1. Check the tasks above and see what is unassigned or needs help.
2. Fork the repository and implement your changes.
3. Submit a pull request detailing your contributions.

---

# Project Overview: DnD GUI with Llama LLM Backend  

This project aims to deliver the rich storytelling and immersive gameplay of **Dungeons & Dragons (DnD)** through a Python-based GUI platform, powered by a Llama large language model (LLM). The interface will simulate a virtual table with players and a Dungeon Master (DM), all while incorporating innovative features such as customizable personas, interactive character sheets, and dynamic voice capabilities.  

---

## Key Features  

### 🧙‍♂️ Character Personas and Custom Voices  
Each player at the table will have two layers of personas, each capable of independent voice processing:  
1. **Personal Persona**: Reflects the player’s real-world traits and interacts with the table. Each personal persona will have:  
   - A **customizable voice** using pre-recorded samples (e.g., your real voice).  
   - Realistic, AI-powered speech synthesis for dialogue during gameplay.  
2. **Character Persona**: The fictional DnD character the player controls in the game, complete with a **distinct voice** tailored to fit their personality and species.  
   - Example: A Dragonborn berserker named Socks might speak with a deep, theatrical voice inspired by Vincent Price's Dracula.  

Voice configuration will support:  
- **Recording Samples**: Players can upload their voice recordings to train the system.  
- **Voice Selection**: AI-generated voices can be chosen from a library of tones and accents to align with each character’s persona.  

---

### 🎲 DnD Mechanics  
- **Character Sheets**: Includes traditional DnD stats like Strength, Dexterity, Charisma, and more, generated through dice rolls or manual input.  
- **Figurines**: Visual representations of each character on the virtual tabletop.  
- **Dungeon Master (DM) Tools**:  
  - The DM can dynamically guide gameplay using tools to manage NPCs, health, and combat scenarios.  
  - The DM's **arena interface** will allow them to interact with the environment using AI-generated inputs and pre-set rules.  
- **Physical and Digital Game Sheets**:  
  - Players and the DM can use digital sheets for gameplay, with optional printed versions for a traditional feel.  

---

### 🎙 Advanced Voice Features  
To bring the game to life, the system will include:  
- **Speech Recognition**: Players can interact with the game using their voice, which will be processed and responded to by the LLM or other players’ personas.  
- **Individualized Voices**:  
  - Each player’s **personal persona** will have its own voice for conversations at the table.  
  - Each player’s **character persona** will have a distinct voice for in-game interactions with the DM, NPCs, and other characters.  
- **Real-Time Voice Processing**: Voices will dynamically switch depending on whether the player is speaking as themselves or as their in-game character.  

---

### 🤖 LLM-Powered Dungeon Master  
The LLM will serve as a co-narrator, managing NPC dialogue, random events, and interactions with the environment. The DM's tools will leverage the LLM to provide natural, context-aware responses and immersive storytelling.  

---

### 🎮 Flexible Gameplay Modes  
- **Local Play**: Fully functional gameplay on a single machine, with a focus on voice features and GUI-driven interactions.  
- **Future Expansion**: Multiplayer support will allow remote players to connect and participate with their characters and personas.  

---

## 🛠 Development Workflow  
The project will be developed in **two-week sprints**, focusing on implementing core features first and expanding voice and AI functionality in later iterations.  

### Target Milestones  
1. **Sprint 1**: Develop the core GUI, integrate character sheets, and enable basic LLM interactions for local play.  
2. **Sprint 2**: Add DM tools, refine gameplay mechanics, and implement basic voice processing.  
3. **Sprint 3 and Beyond**: Expand voice synthesis capabilities, improve speech recognition, and introduce remote gameplay options.  

---

This project aims to combine the rich tradition of tabletop RPGs with cutting-edge AI technology, delivering an experience that feels both authentic and innovative. The unique voices for both players and their characters will add a compelling dimension to the gameplay, creating a fully immersive DnD experience.  

---  

