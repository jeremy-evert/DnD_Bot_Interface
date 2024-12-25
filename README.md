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
