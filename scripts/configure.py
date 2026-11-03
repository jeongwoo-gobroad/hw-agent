"""Interactive EN/KO setup. Secrets stay in .env; existing keys are preserved."""
import argparse
import getpass
import ipaddress
import os
from pathlib import Path
import secrets
import socket
from urllib.parse import urlparse
from dotenv import dotenv_values, set_key

ROOT=Path(__file__).resolve().parents[1]


def public_origin(value):
    url=urlparse(value)
    if (url.scheme!='https' or not url.hostname or url.username or url.password
            or url.query or url.fragment or url.path not in {'','/'} or url.port not in {None,443}):
        raise ValueError('Enter an HTTPS origin, without path, credentials or query')
    if not all(c.isalnum() or c in '.-' for c in url.hostname):
        raise ValueError('Invalid hostname')
    return 'https://'+url.hostname


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lang',choices=['en','ko'],default='en')
    parser.add_argument('--smartthings',action='store_true')
    args=parser.parse_args()
    def text(en,ko):return ko if args.lang=='ko' else en
    target=ROOT/'.env'
    if not target.exists():
        fd=os.open(target,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
    settings=dotenv_values(target)
    def save(key,value):
        set_key(target,key,value);settings[key]=value
    if not args.smartthings:
        if not settings.get('SESSION_SECRET') or settings['SESSION_SECRET']=='replace-with-random-secret':
            save('SESSION_SECRET',secrets.token_urlsafe(48))
        username=input(text('Dashboard username (blank keeps existing): ','대시보드 아이디 (빈칸은 기존 값 유지): ')).strip()
        if username:save('DASHBOARD_USERNAME',username)
        password=getpass.getpass(text('Dashboard password (blank keeps existing): ','대시보드 비밀번호 (빈칸은 기존 값 유지): '))
        if password:
            if len(password)<12:raise ValueError(text('Use at least 12 characters.','12자 이상을 사용하세요.'))
            if password!=getpass.getpass(text('Confirm password: ','비밀번호 확인: ')):raise ValueError('Passwords do not match')
            save('DASHBOARD_PASSWORD',password)
        if any(not settings.get(k) or settings[k]=='change-me' for k in ('DASHBOARD_USERNAME','DASHBOARD_PASSWORD')):
            raise ValueError('Set both dashboard credentials')
        hostname=socket.gethostname()
        try:
            addresses=socket.gethostbyname_ex(hostname)[2]
        except socket.gaierror:
            addresses=[]
        default=','.join(dict.fromkeys(['127.0.0.1','localhost',hostname,hostname+'.local',*addresses]))
        hosts=input(text('Allowed hosts, comma-separated (blank keeps defaults): ','허용할 호스트/IP, 쉼표 구분 (빈칸은 기본값): ')).strip()
        save('ALLOWED_HOSTS',hosts or settings.get('ALLOWED_HOSTS') or default)
        lan=input(text('Trusted LAN CIDR (e.g. 192.168.1.0/24): ','내부망 CIDR (예: 192.168.1.0/24): ')).strip()
        save('LAN_CIDR',str(ipaddress.ip_network(lan,strict=True)))
        save('DASHBOARD_URL',settings.get('DASHBOARD_URL') or f'http://{hostname}.local:11977')
    else:
        print(text('Use your own ngrok account and SmartThings OAuth app. SmartThings plan requirements apply.',
                   '본인의 ngrok 계정과 SmartThings OAuth 앱을 사용하세요. SmartThings 요금제 조건이 적용됩니다.'))
        origin=public_origin(input(text('ngrok HTTPS address: ','ngrok HTTPS 주소: ')).strip())
        token=getpass.getpass('ngrok Authtoken (blank keeps existing): ')
        client=input('SmartThings Client ID (blank keeps existing): ').strip()
        secret=getpass.getpass('SmartThings Client Secret (blank keeps existing): ')
        if token:save('NGROK_AUTHTOKEN',token)
        if client:save('SMARTTHINGS_CLIENT_ID',client)
        if secret:save('SMARTTHINGS_CLIENT_SECRET',secret)
        save('SMARTTHINGS_REDIRECT_URI',origin+'/oauth/callback')
        hosts=[h for h in settings.get('ALLOWED_HOSTS','127.0.0.1,localhost').split(',') if h]
        save('ALLOWED_HOSTS',','.join(dict.fromkeys(hosts+[urlparse(origin).hostname])))
        print(text('Register this exact callback in your OAuth app: ','OAuth 앱에 다음 콜백을 정확히 등록하세요: ')+origin+'/oauth/callback')
    os.chmod(target,0o600)
    print(text('Saved. Restart Alter after configuration changes.','저장했습니다. 설정 변경 후 Alter를 재시작하세요.'))


if __name__=='__main__':main()
