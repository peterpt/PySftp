# PySftp
PySFTP is a modern, feature-rich graphical SFTP client built with Python and the CustomTkinter library. It provides a clean, dual-pane interface for managing local and remote files, supports advanced networking features like jump hosts and port knocking, and includes an integrated SSH terminal for full remote control.
## Main gui
<img width="1024" height="741" alt="image" src="https://github.com/user-attachments/assets/58f5be67-a109-48a6-8a97-05a46e4ee353" />

## CLI 
<img width="746" height="559" alt="image" src="https://github.com/user-attachments/assets/0240338e-30b8-48fe-8380-aae28e7261bf" />


## Features

Dual-Pane Interface: Classic and intuitive layout for managing local and remote files side-by-side.

- Secure Connections: Supports standard SFTP connections over SSH.
- Jump Host (Bastion) Support: Connect to a target server through an intermediate jump host for enhanced security.
- Robust Profile Manager:
Save, load, and edit connection profiles.
- Quickly switch between frequently used servers.
- Delete old profiles.
- Port Knocking: Configure and automate port knocking sequences on a per-profile basis to open firewalled ports before connecting.

- Integrated SSH Terminal: Open a fully functional SSH shell to your target or jump host directly from the application.

- File Operations: Supports standard SFTP operations:
Upload and Download (files and recursive directories).
Create Remote Folders.
Move/Rename files and folders.
Delete files and folders.

- Secure Password Handling: Profiles save connection details for convenience but do not store passwords. Passwords are requested just-in-time for each session.

- Command-Line Integration: Launch and auto-connect using CLI arguments for quick sessions.

- Customizable Appearance: Supports system themes (Light/Dark) and allows for custom configuration of terminal colors.

## Requirements

 Python 3.8+
The following Python libraries:
customtkinter
paramiko
Pillow

## Installation

    Clone the repository:
    code Bash
   
git clone https://github.com/peterpt/PySftp.git
cd PySftp


- Install the required libraries:
pip3 install -r requirements.txt
   

## Usage
Graphical Interface (Standard)

To run the application, simply execute the pysftp.py script:
code Bash
   
python3 pysftp.py

  

## Command-Line Arguments

For quick, one-off connections, you can provide connection details as command-line arguments. The application will launch and attempt to connect automatically.

- Basic Connection:
code Bash
    
python3 pysftp.py -H your-server.com -u your-username --port 22

  
 - Connection via Jump Host:
code Bash
   
python3 pysftp.py -H 192.168.1.100 -u target_user --jump-host bastion.your-server.com --jump-user jump_user

- If a password is not provided via the -p or --jump-password flags, a dialog will pop up to securely ask for it.

## Configuration (config.ini)

The application saves profiles and settings in a config.ini file in the same directory.
Profile Structure

Each saved profile is a section in the .ini file. Passwords are never saved.

Example Profile:
code Ini

    
[MyWebServer]
host = my-server.com
user = webadmin
port = 2222
use_jump = false
knock_enabled = true
knock_ports = 7000,8000,9000
knock_delay = 1.0

[InternalServer]
host = 10.0.1.50
user = internal_user
port = 22
use_jump = true
jump_host = bastion.my-company.com
jump_user = bastion_user
jump_port = 22
knock_enabled = false
knock_ports = 
knock_delay = 1

  

Settings

The [Settings] section stores UI customizations, such as terminal colors.
code Ini

    
[Settings]
terminal_bg = #000000
terminal_fg = #FFFFFF

  

✍️ Author & Credits

Author: peterpt

AI Collaboration: Conceptual design, feature implementation, and extensive debugging in collaboration with Gemini, a large language model from Google.

📜 License

This project is licensed under the MIT License. See the LICENSE file for details.
