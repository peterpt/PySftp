import paramiko
import os
import stat
import time
import socket # <-- IMPORT THE SOCKET LIBRARY
from paramiko.sftp_client import SFTPClient

# --- NEW PORT KNOCKING FUNCTION ---
def perform_port_knock(host, ports, delay):
    """
    Performs a port knocking sequence using pure Python sockets.

    Args:
        host (str): The hostname or IP address to knock on.
        ports (list): A list of integer ports to knock on in sequence.
        delay (float): The time in seconds to wait between each knock.

    Returns:
        tuple: (bool, str) indicating success and a message.
    """
    print(f"Starting port knocking sequence for {host} on ports: {ports}")
    try:
        # Resolve hostname to IP address once
        ip_address = socket.gethostbyname(host)
        for port in ports:
            print(f"Knocking on port: {port}")
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                # Set a very short timeout. We don't need to complete the connection.
                s.settimeout(0.2)
                try:
                    # The knock is the connection attempt itself. We ignore the result.
                    s.connect((ip_address, port))
                except (socket.timeout, ConnectionRefusedError):
                    # This is the expected outcome for a closed port.
                    pass
                except Exception as e:
                    # Catch other potential errors, but don't stop the sequence.
                    print(f"  (Ignoring error during knock: {e})")
            # Wait for the specified delay
            time.sleep(delay)
        print("Port knocking sequence completed.")
        return True, "Port knocking sequence completed successfully."
    except socket.gaierror:
        return False, f"Hostname '{host}' could not be resolved."
    except Exception as e:
        return False, f"An unexpected error occurred during port knocking: {e}"

# --- MODIFIED connect_sftp (no changes, just context) ---
def connect_sftp(target_host, target_port, target_user, target_pass,
                 jump_host=None, jump_port=None, jump_user=None, jump_pass=None):
    # This function remains the same, with the retry loop
    max_retries = 5
    retry_delay = 2

    for attempt in range(max_retries):
        jump_client = None
        try:
            if jump_host:
                jump_client = paramiko.SSHClient()
                jump_client.load_system_host_keys()
                jump_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                print(f"(Attempt {attempt + 1}/{max_retries}) Connecting to jump host {jump_user}@{jump_host}...")
                jump_client.connect(hostname=jump_host, port=jump_port, username=jump_user, password=jump_pass, timeout=10)
                jump_transport = jump_client.get_transport()
                dest_addr = (target_host, target_port)
                local_addr = ('127.0.0.1', 0)
                channel = jump_transport.open_channel("direct-tcpip", dest_addr, local_addr)
                target_client = paramiko.SSHClient()
                target_client.load_system_host_keys()
                target_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                print(f"Connecting to target host {target_user}@{target_host} via tunnel...")
                target_client.connect(hostname=target_host, username=target_user, password=target_pass, sock=channel)
                return jump_client, target_client, None

            else:
                target_client = paramiko.SSHClient()
                target_client.load_system_host_keys()
                target_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                print(f"(Attempt {attempt + 1}/{max_retries}) Connecting directly to {target_user}@{target_host}...")
                target_client.connect(hostname=target_host, port=target_port, username=target_user, password=target_pass, timeout=10)
                return None, target_client, None

        except Exception as e:
            error_message = f"Connection failed on attempt {attempt + 1}: {e}"
            print(f"Error: {error_message}")
            if jump_client:
                jump_client.close()
            if attempt < max_retries - 1:
                print(f"Waiting {retry_delay} seconds before retrying...")
                time.sleep(retry_delay)
            else:
                print("Max retries reached. Giving up.")
                return None, None, error_message

    return None, None, "Connection failed after all retries."

# --- ROBUST SFTP & OTHER FUNCTIONS (Unchanged) ---
def open_sftp_robust(ssh_client):
    transport = ssh_client.get_transport()
    sftp_server_paths = ["/usr/lib/sftp-server", "/usr/lib/openssh/sftp-server", "/usr/libexec/openssh/sftp-server", "sftp-server"]
    last_exception = None
    for path in sftp_server_paths:
        try:
            channel = transport.open_session()
            channel.exec_command(f"exec {path}")
            sftp_client = SFTPClient(channel)
            print(f"Successfully started SFTP using robust exec method with path: {path}")
            return sftp_client
        except Exception as e:
            last_exception = e
            print(f"Robust SFTP exec method failed for path '{path}': {e}")
            if channel and channel.active:
                channel.close()
    raise Exception(f"Could not find a valid sftp-server binary to execute on the remote host. Last error: {last_exception}")

def upload_file(sftp, local_path, remote_path):
    try: sftp.put(local_path, remote_path); return True, f"Uploaded {os.path.basename(local_path)}"
    except Exception as e: return False, f"Upload failed: {e}"

def download_remote_item(sftp, remote_path, local_path):
    try:
        if stat.S_ISDIR(sftp.stat(remote_path).st_mode): _download_directory_recursive(sftp, remote_path, local_path); return True, f"Downloaded dir '{os.path.basename(remote_path)}'"
        else: sftp.get(remote_path, local_path); return True, f"Downloaded file '{os.path.basename(remote_path)}'"
    except Exception as e: return False, f"Download failed: {e}"

def _download_directory_recursive(sftp, remote_dir, local_dir):
    os.makedirs(local_dir, exist_ok=True)
    for item in sftp.listdir_attr(remote_dir):
        r_path = f"{remote_dir}/{item.filename}".replace('//', '/'); l_path = os.path.join(local_dir, item.filename)
        if stat.S_ISDIR(item.st_mode): _download_directory_recursive(sftp, r_path, l_path)
        else: sftp.get(r_path, l_path)

def rename_remote_item(sftp, old_path, new_path):
    try: sftp.rename(old_path, new_path); return True, f"Moved to '{new_path}'"
    except Exception as e: return False, f"Error moving: {e}"

def delete_remote_item(sftp, path):
    try:
        if stat.S_ISDIR(sftp.stat(path).st_mode):
            files = sftp.listdir(path)
            if not files:
                sftp.rmdir(path)
            else:
                for f in files:
                    filepath = f"{path}/{f}".replace("//", "/")
                    delete_remote_item(sftp, filepath)
                sftp.rmdir(path)
            return True, f"Deleted directory '{os.path.basename(path)}'"
        else:
            sftp.remove(path)
            return True, f"Deleted file '{os.path.basename(path)}'"
    except Exception as e:
        return False, f"Error deleting: {e}"

def create_remote_directory(sftp, path):
    try: sftp.mkdir(path); return True, f"Created directory '{os.path.basename(path)}'"
    except Exception as e: return False, f"Error creating directory: {e}"

