# DnD_Bot_Interface
Building a backend that will let me play dungeons and dragons with a chatbot and have the documents to make everything work.


# TODO List

Here are the tasks planned for the DnD GUI project using Llama LLM. Tasks are numbered for easier tracking, and dependencies are clearly marked.

---

## 🧑‍💻 Team Members
| Name           | Email                        | Phone        | Initials |
|----------------|------------------------------|--------------|----------|
| Jeremy Evert   | jeremy.evert@swosu.edu       | 785-443-0967 | JE       |

---

## 🚀 Features
| #   | Task                                                   | Assigned To | Dependencies |
|-----|--------------------------------------------------------|-------------|--------------|
| 1   | Design the virtual table GUI layout                   |             | None         |
| 2   | Implement multi-character interaction capabilities     |             | 1            |
| 3   | Integrate Llama LLM as the backend                    |             | None         |
| 4   | Add character sheet customization functionality        |             | 2, 3         |
| 5   | Create save/load game state functionality             |             | 4            |

---

## 🛠 Development Steps
| #   | Step                                                     | Assigned To | Dependencies |
|-----|----------------------------------------------------------|-------------|--------------|
| 1   | Set up the Python environment and dependencies          | JE          | None         |
| 2   | Install and configure Llama LLM locally                 |             | 1            |
| 3   | Refactor modular code architecture                      |             | None         |
| 4   | Test Llama integration with sample prompts              |             | 2            |
| 5   | Optimize LLM query responses for low-latency performance |             | 4            |
| 6   | Add error handling for GUI interactions                 |             | 3, 5         |
| 7   | Create unit tests for GUI functionality                 |             | 6            |

---

## 📖 Documentation
| #   | Task                                                     | Assigned To | Dependencies |
|-----|----------------------------------------------------------|-------------|--------------|
| 1   | Write project overview in `README.md`                   |             | None         |
| 2   | Document installation and setup process                 |             | 1 (Dev Steps)|
| 3   | Create examples of usage with screenshots               |             | 1-5 (Dev Steps)|

---

## 🐛 Bug Fixes
| #   | Bug                                                     | Assigned To | Dependencies |
|-----|----------------------------------------------------------|-------------|--------------|
| 1   | Fix GUI layout issues for small screens                |             | 1 (Features) |
| 2   | Resolve intermittent crashes during LLM responses      |             | 5 (Dev Steps)|

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

