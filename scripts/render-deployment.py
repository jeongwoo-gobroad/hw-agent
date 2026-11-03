"""Render installation templates for the current Linux account; no service changes."""
import argparse
import ipaddress
import os
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]


def render(source, *, user, group, home, root, uid, gid, lan, ngrok='/usr/bin/ngrok'):
    for value in (user, group):
        if not re.fullmatch(r"[a-z_][a-z0-9_-]*\$?", value):
            raise ValueError("Use a valid Linux account name")
    for value in (home, root, ngrok):
        if not re.fullmatch(r"/[A-Za-z0-9_./-]+", value) or '..' in Path(value).parts:
            raise ValueError("Install paths must be absolute and contain no spaces or shell metacharacters")
    network = str(ipaddress.ip_network(lan, strict=True))
    values = {"USER":user, "GROUP":group, "HOME":home, "ROOT":root,
              "UID":str(int(uid)), "GID":str(int(gid)), "LAN":network, "NGROK":ngrok}
    for key, value in values.items():
        source = source.replace('@'+key+'@', value)
    if re.search(r'@[A-Z_]+@', source):
        raise ValueError("Unresolved deployment placeholder")
    return source


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lan', required=True, help='Trusted LAN CIDR, e.g. 192.168.1.0/24')
    parser.add_argument('--output', type=Path, default=ROOT/'data/deploy')
    args=parser.parse_args()
    if os.getuid()==0:
        parser.error('Run as the Pi account, without sudo')
    import pwd, grp
    account=pwd.getpwuid(os.getuid())
    values=dict(user=account.pw_name,group=grp.getgrgid(account.pw_gid).gr_name,
                home=account.pw_dir,root=str(ROOT),uid=account.pw_uid,gid=account.pw_gid,lan=args.lan,
                ngrok=shutil.which('ngrok') or '/usr/bin/ngrok')
    args.output.mkdir(parents=True,exist_ok=True,mode=0o700)
    for source in (ROOT/'deploy').iterdir():
        if source.is_file():
            (args.output/source.name).write_text(render(source.read_text(),**values),encoding='utf8')
    (ROOT/'Start-Alter.desktop').write_text(render((ROOT/'deploy/alter-start.desktop').read_text(),**values),encoding='utf8')
    (args.output/'alter-sudoers').write_text(
        f'{account.pw_name} ALL=(root) NOPASSWD: /usr/local/sbin/alter-smb, /usr/local/sbin/alter-disk\n')


if __name__=='__main__':
    main()
