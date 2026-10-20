"""Publish tracked sources, preserving private device state."""
import argparse
import base64
import getpass
import hashlib
from pathlib import Path
import subprocess
import paramiko
from tqdm import tqdm

parser = argparse.ArgumentParser()
parser.add_argument("--host", default="192.168.0.44")
parser.add_argument("--user", default="jeongwoo")
parser.add_argument("--fingerprint", default="OSnOzU8jFkJqX7e3CmTnXg6b5SGr8jblKjYcnHdmqpo=")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]


class Pinned(paramiko.MissingHostKeyPolicy):
    def missing_host_key(self, client, hostname, key):
        actual = base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode()
        if actual != args.fingerprint:
            raise RuntimeError("SSH host key mismatch")


client = paramiko.SSHClient()
client.set_missing_host_key_policy(Pinned())
client.connect(args.host, username=args.user, password=getpass.getpass("SSH password: "), timeout=20)
sftp = client.open_sftp()
files = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0")
for relative in tqdm([p for p in files if p], desc="Deploy"):
    target = f"/home/{args.user}/hw-agent/" + relative
    parts = target.split("/")
    for index in range(4, len(parts)):
        try:
            sftp.mkdir("/".join(parts[:index]))
        except OSError:
            pass
    sftp.put(str(root / relative), target)
    with sftp.open(target, "rb") as remote:
        if hashlib.sha256(remote.read()).digest() != hashlib.sha256((root/relative).read_bytes()).digest():
            raise RuntimeError("Deployment hash mismatch: " + relative)
sftp.close()
client.close()
print("Source synchronized. Restart alter after dependency/migration checks.")
