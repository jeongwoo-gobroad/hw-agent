# NTFS 압축과 SMB 읽기 점검

## 현재 작업 범위

USB를 Pi에 연결한 상태에서 Windows 기본 NTFS 기능으로 압축 해제를 수행하는 절차를 검증한다. 파일 내용은 진단 출력이나 모델 입력으로 보내지 않는다. 압축 변환 자체의 데이터 처리는 운영체제가 담당한다.

## 2026-10-30 초기 진단

- 운영 NTFS 드라이브는 `ntfs3`로 읽기/쓰기 마운트되어 있었다. 공유 대상 폴더와 해당 볼륨 루트에 NTFS 압축 속성이 설정되어 있었다.
- 커널 `6.18.50+rpt-rpi-2712`, 페이지 크기 16KiB 환경에서 10월 27일 SMB 작업이 `ntfs_read_folio`의 mutex와 `ni_read_folio_cmpr`의 페이지 대기에서 120초 이상 멈춘 기록을 확인했다. 압축 읽기 경로가 관련되어 있다는 증거이며 파일 손상이나 정확한 커널 결함까지 확정한 것은 아니다.
- 공유 최상위의 새 시험 파일 139,264바이트를 Pi에서 생성하고 읽어 내용 일치를 확인했다. 비어 있지 않은 시험 파일의 `system.ntfs_attrib_be` 압축 비트 해제는 `EOPNOTSUPP`(95)로 거부되었다. 실패 전후 내용이 같았고 시험 파일을 삭제했다.
- 기존 압축 JPEG 3개(1,602,752 / 1,383,556 / 826,734바이트)는 Pi 직접 읽기와 Windows SMB 읽기의 SHA-256이 각각 일치했다. 이는 표본 검사이며 간헐적 멈춤의 해결이나 전체 데이터 무결성을 뜻하지 않는다.
- Windows SMB 경유 시험 파일 생성·압축 해제·삭제 검증은 실행 승인 검토에서 차단되어 실행하지 못했다. SMB 압축 해제 지원 여부는 실제 검증되지 않았다.
- 초기 진단 시점의 남은 공간은 약239.5GiB였다. 이후 메타데이터 조사로 압축 해제에 필요한 할당 증가분을 집계했다.
- 초기 진단에서는 기존 사용자 파일·폴더의 압축 속성, 마운트 설정, 서비스 설정을 변경하지 않았다. 이후 운영 변환을 시작했으며, 아래 진행 상태와 구분한다.

## 2026-10-30 iSCSI 현장 검증

- `tgt`를 설치하고 loopback에만 바인딩했다. Windows도 loopback 포털을 사용하며 두 포털 사이의 전송은 호스트 키를 고정한 SSH 터널로 보호한다. CHAP 인증을 함께 적용했다.
- 새 256MiB MBR/NTFS 시험 이미지에서 Windows 연결, 기본 NTFS 압축 해제, 정상 연결 해제를 검증했다. 서로 다른 파일과 하드링크를 구분했으며 합성 내용과 추가 데이터 스트림을 보존했다. Pi에서 다시 읽어 원문의 SHA-256 및 하드링크 inode 일치를 확인했다.
- Windows 작업 관리자의 디스크 감시가 장치 제거를 거부하는 것을 이벤트 225로 확인했다. 해당 창을 닫은 뒤 정상 분리되었다. 파일시스템을 두 OS에서 동시에 마운트하는 방식은 사용하지 않는다.
- 운영 변환용 작업은 내용을 읽는 대신 파일 속성, 파일 ID, 논리/할당 크기와 스트림 메타데이터를 조사한다. SQLite에 진행 상태를 저장하고 여유 공간을 확인한 후 `FSCTL_SET_COMPRESSION`을 호출한다. 재분석 지점은 따라가지 않는다. 개별 경로와 작업 DB는 로컬 비공개 상태로 보관한다.
- 운영 볼륨 준비 중 기존 SMB 스레드들이 `ntfs_read_folio`와 `folio_wait_bit_common`에서 종료되지 않는 것을 확인했다. 서버·색인을 중지하고, 재부팅 중 자동 마운트/서비스 재시작을 막는 유지보수 조건을 적용했다. Pi 재시작 후 대상 볼륨이 Linux에 마운트되지 않은 것을 확인하고 Windows 단독 연결에서 메타데이터 조사를 시작했다. 운영 압축 해제 완료로 기록하지 않는다.

### 운영 변환 진행 상태

메타데이터 조사와 여유 공간 검사를 마치고 Windows 기본 NTFS 압축 해제를 실행 중이다. 폴더 기본 압축 속성과 기존 데이터 스트림을 따로 처리한다. **전체 변환, Pi 공유 복구, 복구 후 SMB 읽기·쓰기 검증은 아직 완료되지 않았다.**

변환은 파일 ID와 스트림별 SQLite 기록을 기준으로 재개한다. 재개 시 이미 압축이 해제된 항목은 상태 조회만 하고 다시 변환하지 않는다. 제자리 변환의 공간 검사는 파일 전체 크기가 아닌 현재 할당 크기 대비 증가분과 별도 예비 공간을 사용한다. 큰 파일의 Windows 호출 하나가 오래 걸릴 수 있으므로 진행 기록의 갱신 지연만으로 중단된 작업이라고 판단하지 않는다.

한 번 승인받은 관리자 셸에서 필요한 작업을 순서대로 실행한다. 대기열과 작업 상태는 로컬의 제한된 디렉터리에 두며 저장소에는 포함하지 않는다. 후속 처리는 Windows 연결 해제가 확인되고 Pi 대상에도 연결이 없을 때만 Linux 소유권을 복구한다. 분리가 확인되지 않으면 마운트 방지 상태를 유지한다. 복구 확인에 실패하면 완료로 처리하지 않는다. 작업 재개와 복구 분기에는 모의 검증을 적용했으며, 이를 실제 운영 변환 완료 검증과 구분한다.

일부 항목의 접근 거부는 첫 변환이 끝난 뒤 Windows 기본 `compact`로 한 번 재시도한다. 합성 파일에서 직접 변환 호출의 접근 거부를 재현한 후 `compact`가 읽기 전용·숨김·시스템 속성과 내용을 보존하며 압축을 해제하는 것을 확인했다. 재시도는 볼륨·파일 ID를 확인하고 압축 해제 및 기존 속성 보존을 검증한 뒤 완료로 기록한다. 기존 ACL을 바꾸거나 와일드카드로 범위를 넓히지 않는다. 합성 검증은 실제 오류 파일들의 재시도 성공을 보장하지 않는다.

보안 프로그램 차단은 접근 권한 오류와 별도로 기록한다. 해당 항목은 자동 재시도·격리 복원 대상에서 제외하며 보안 설정을 변경하지 않는다. 보안 프로그램이 원본 위치에서 파일을 격리한 경우에는 전체 압축 해제 성공으로 합산하지 않는다. 최종 결과는 처리 완료·남은 오류·보안 차단을 구분해 확인한다.

### PowerShell 진행 화면

`scripts/watch-ntfs-progress.ps1`은 관리자 권한 없이 5초 간격으로 진행 상태를 표시한다. `-StateDirectory`에 유지보수 상태 폴더, `-DiskSerial`에 Windows에서 확인한 iSCSI 디스크 일련번호를 지정한다. Python 실행 위치는 `-Python`으로 지정할 수 있다. `-Once`는 한 번만 출력하며, 기본 실행은 창을 닫거나 Ctrl+C를 누를 때까지 표시한다. 화면을 종료해도 변환 작업은 계속된다.

상태 폴더의 `real-worker/inventory.sqlite3`, `real-worker/progress.json`, `real-maintenance-result.json`, `maintenance-supervisor.json`, `restoration-result.json`을 사용한다. `ntfs_progress_snapshot.py --state-directory <상태 폴더>`가 읽기 전용 SQLite 집계와 상태 JSON을 제공한다. 원본 파일이나 파일 경로는 조회·출력하지 않는다. 오류 메시지 원문도 표시하지 않는다.

완료 데이터 건수·완료 용량·폴더 속성·오류 수는 DB에 기록된 확정 결과다. 데이터 건수는 추가 데이터 스트림을 포함하므로 실제 파일 수와 다를 수 있다. 큰 파일 내부의 진행률과 정확한 ETA는 제공하지 않는다. 이때 완료 수가 바뀌지 않아도 Windows 디스크 성능 카운터의 읽기·쓰기 속도로 I/O가 계속되는지 확인할 수 있다. 용량 백분율은 완료된 스트림만 포함하며 디스크 전송량을 완료량으로 간주하지 않는다. Windows 연결 해제·Pi 복구 단계에는 장치/속도 조회를 중단한다.

## 연결을 유지하는 방법 조사

**USB를 Windows PC에 물리적으로 옮겨야 한다는 이전 판단을 정정한다.** Pi에서 디스크를 iSCSI로 제공하고 Windows가 그 디스크를 단독으로 마운트하면, 케이블을 옮기지 않고 Windows의 NTFS 압축 해제 기능을 사용할 수 있는 구성이 된다. 아래 판단은 공식 문서·소스와 설치 환경 점검에 근거하며, 합성 iSCSI 시험 결과와 운영 파일 압축 해제 결과를 구분한다.

| 방법 | 확인 결과 | 현재 선택 |
|---|---|---|
| 기존 Samba 공유에서 `compact /u` | 설치 버전 4.22.11의 기본 VFS `vfswrap_set_compression`은 `NT_STATUS_INVALID_DEVICE_REQUEST`를 반환한다. 현재 공유는 압축 전환 전용 VFS를 사용하지 않는다. Btrfs용 VFS는 NTFS 해법이 아니다. | 현재 구성으로는 사용하지 않음 |
| NTFS3 속성 해제 | 실제 시험 파일에서 `EOPNOTSUPP` 확인. 비어 있지 않은 일반 NTFS 압축 파일의 제자리 변환을 지원하지 않음. | 사용하지 않음 |
| NTFS-3G `nocompression` 또는 파일 `setfattr` | 기존 파일 압축은 유지된다. 합성 이미지에서 실제 확인. | 새 파일의 압축 방지와 읽기 드라이버 교체 후보일 뿐 전체 해제 방법은 아님 |
| NTFS-3G에서 비압축 복사본 생성 후 교체 | 합성 시험에서 비압축 복사 성공. 파일 식별자가 달라짐. 스트림·ACL·생성 시간·하드링크·충돌·복구를 별도로 보존해야 함. | 원본을 자동 교체하지 않음 |
| Pi iSCSI + Windows NTFS | `tgt`가 로컬 블록 장치를 제공하고 Windows 기본 iSCSI Initiator가 연결하는 구성. 파일별 변환은 Windows `FSCTL_SET_COMPRESSION` 또는 `compact /u` 사용. | 합성 시험 통과, 운영 변환 진행 중 |
| USB/IP + Windows 수신 드라이버 | 검토한 `usbip-win`은 테스트 서명/재부팅 안내와 생산 환경 미준비 경고가 있다. `usbipd-win`은 Windows USB를 다른 장치로 내보내는 방향이므로 대체 수신 드라이버가 아니다. | iSCSI보다 우선하지 않음 |
| 상용 Paragon UFSD | 2011년 공식 8.5 설명서에는 `fsutil compress clearflag`가 있다. 현재 Pi ARM64/6.18 커널용 배포물·라이선스·실제 동작은 확인하지 못함. | 즉시 사용할 수 있다고 주장하지 않음 |
| 새 커널의 `ntfs` 드라이버 | 최신 문서에서도 `chattr`로 압축 속성을 바꾸는 기능은 지원하지 않는다. 커널 교체 자체는 압축 해제 방법이 아니다. | 이 작업만을 위해 커널을 바꾸지 않음 |

### Pi의 독립 합성 시험

운영 외장 드라이브를 사용하지 않고 SD카드의 `data/` 아래 새 96MiB 이미지 파일을 만들었다. `mkntfs`의 대상은 이 새 일반 파일뿐이었다. NTFS-3G 2022.10.3으로 마운트해 합성 자료만 처리했다.

- 합성 파일: 논리 크기 2,293,760바이트, 압축 할당 크기 286,720바이트.
- 압축 비트를 지우는 `setxattr`는 성공을 반환했지만 다시 조회하면 압축 비트가 그대로였다. 이는 해당 버전 `security.c`가 일반 파일의 압축 비트를 변경 가능한 비트에 포함하지 않는 구현과 일치한다.
- 정상 마운트 해제 후 `nocompression`으로 다시 마운트해도 기존 파일의 압축 비트가 유지되었다.
- 비압축 복사본은 압축 비트가 꺼졌고 합성 원문과 내용이 일치했다. 원본/복사본 inode는 각각65/66이었다.
- 시험 이미지는 정상 마운트 해제했다. 운영 드라이브·공유·색인 서비스에는 변경을 적용하지 않았다.

### iSCSI 전제 조건의 실제 확인

- Pi 커널에서 `CONFIG_TARGET_CORE`가 비활성화되어 있어 일반 `targetcli`/LIO 구성은 그대로 사용할 수 없다.
- 대안인 `tgt`는 사용자 공간 iSCSI 구현이다. Pi의 ARM64 패키지를 설치했고 합성 시험을 완료했다. 서비스 시작 시 전체 주소에 기본 노출하지 않는다. LAN 주소 한정 구성 또는 loopback 바인딩과 SSH 포워딩 구성이 가능하며, 후자의 Windows 연결과 정상 분리를 합성 디스크로 검증했다.
- PC에 `MSiSCSI`, `Connect-IscsiTarget`, `Get-IscsiSession`, `Get-Disk`가 있다. 최초 연결 이후 동일한 관리자 세션을 유지해 작업을 실행한다.
- iSCSI 연결·Windows 변환·Pi 재마운트까지 합성 시험을 완료했다. 운영 데이터 처리 결과는 별도로 기록한다.

## iSCSI를 이용한 후속 절차

1. 합성 이미지로 Pi `tgt` → PC iSCSI → Windows 압축 해제 → 정상 연결 해제 시험을 완료한다. 대상 IQN·고유 디스크 식별자·크기를 검사하고, 시험 디스크 외에는 온라인 전환이나 드라이브 문자 할당을 하지 않는다.
2. 실제 대상의 UUID와 부모 디스크를 확인한다. 해당 드라이브를 사용하는 SMB·색인·파일 작업을 중지하고 Pi의 정상 마운트 해제 성공을 확인한다. 강제·지연 해제는 사용하지 않는다. 자동 마운트와 부팅 복구가 다시 디스크를 잡지 않도록 유지보수 상태를 적용한다.
3. 디스크 전체를 내보내는 경우 그 디스크의 모든 파티션이 Pi에서 해제되어 있어야 한다. Windows와 Pi가 같은 NTFS 볼륨을 동시에 마운트하면 안 된다. 다른 외장 디스크와 SD카드는 내보내지 않는다.
4. PC 한 대만 접근하도록 접속 제한·CHAP 인증을 적용한다. 인터넷 포트포워딩과 ngrok은 사용하지 않는다. CHAP은 인증 수단이며 전송 암호화는 아니다. 전송 보호에는 SSH 로컬 포워딩 등 암호화 경로를 우선 시험한다. SSH를 사용하면 Pi의 `tgtd`와 PC 포워딩 소켓 모두 loopback에 바인딩하고, iSCSI 포털 주소·포트 및 재연결이 터널을 유지하는지 합성 디스크로 먼저 확인한다.
5. Windows에서 기존 NTFS 파티션과 볼륨 일련번호·용량을 확인한다. **초기화·포맷·파티션 재생성은 하지 않는다.** 드라이브 문자만으로 장치를 판단하지 않는다.
6. 내용 읽기 없이 파일 속성·논리 크기·할당 크기로 공간을 확인하고 상태를 저장한다. 개별 파일 경로와 내용은 공개 로그에 기록하지 않는다. 재분석 지점은 따라가지 않는다. 하드링크는 파일 ID로 중복을 구분하고 이름별로 원본을 교체하지 않는다.
7. Windows의 파일별 압축 해제 기능으로 처리한다. 압축 해제에는 OS 내부의 데이터 읽기/쓰기가 필요하지만 분석용 `ReadFile`·미리보기·검색·해시 검사는 실행하지 않는다. 결과 확인은 압축 상태, 오류 코드, 처리 수와 남은 공간을 사용한다. 폴더 기본 속성과 기존 파일 압축을 별도로 처리한다.
8. Windows 파일시스템을 정상 해제하고 iSCSI 연결/대상을 제거한 뒤에만 Pi에서 다시 마운트한다. UUID 기반 공유·색인 복원과 합성 시험 파일의 SMB 읽기/쓰기를 확인한다. 기존 색인 DB와 접근 제외 설정은 유지한다.

읽기 멈춤 완화만 필요하다면 `ntfs3`에서 `ntfs-3g`로 정상 재마운트하는 별도 방안도 있다. 압축 읽기 구현이 달라지는 것이므로 현장 검증이 필요하며, 이를 전체 압축 해제로 보고하지 않는다. 압축 읽기의 잠금 순서 문제를 고치는 [공식 커널 커밋](https://github.com/torvalds/linux/commit/e37a75bb866c29da954b51d0dd7670406246d9ee)도 확인했지만 현재 Pi 현상의 정확한 원인/해결 버전과 동일하다고 확정하지 않는다.

## 근거

- [Linux NTFS3 문서](https://docs.kernel.org/filesystems/ntfs3.html): `system.ntfs_attrib`의 압축/희소 속성 전환 제약.
- [Raspberry Pi NTFS3 구현](https://github.com/raspberrypi/linux/blob/rpi-6.18.y/fs/ntfs3/frecord.c): `ni_new_attr_flags`에서 비어 있지 않은 nonresident 데이터의 전환을 거부한다. 브랜치 내용은 변경될 수 있으며 운영 장비 시험 결과와 구분한다.
- [Microsoft compact](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/compact): 폴더 기본 압축 속성과 기존 파일 상태, 재귀 옵션의 범위.
- [Microsoft FSCTL_SET_COMPRESSION](https://learn.microsoft.com/en-us/windows/win32/api/winioctl/ni-winioctl-fsctl_set_compression): 운영체제의 파일별 압축 상태 변경 기능. SMB 프로토콜 지원이 개별 Samba 서버의 구현 지원을 보장하지는 않는다.
- [Samba 4.22.11 기본 VFS](https://github.com/samba-team/samba/blob/samba-4.22.11/source3/modules/vfs_default.c): `vfswrap_set_compression` 구현.
- [NTFS-3G 2022.10.3 속성 처리](https://github.com/tuxera/ntfs-3g/blob/2022.10.3/libntfs-3g/security.c): `FILE_ATTR_SETTABLE`, `ntfs_set_ntfs_attrib`.
- [NTFS-3G 압축 설명](https://github.com/tuxera/ntfs-3g/wiki/Using-Transparently-Compressed-Files), [Debian NTFS-3G 매뉴얼](https://manpages.debian.org/trixie/ntfs-3g/ntfs-3g.8.en.html): 새 파일과 기존 파일의 압축 동작 구분.
- [TGT 공식 저장소](https://github.com/fujita/tgt), [tgtd](https://manpages.debian.org/trixie/tgt/tgtd.8.en.html), [targets.conf](https://manpages.debian.org/trixie/tgt/targets.conf.5.en.html): 사용자 공간 구현, LAN 바인딩, 로컬 블록 장치, 접속 제한과 인증.
- [Microsoft Connect-IscsiTarget](https://learn.microsoft.com/en-us/powershell/module/iscsi/connect-iscsitarget): Windows 연결 인터페이스.
- [OpenSSH 매뉴얼](https://man.openbsd.org/ssh): `-L` TCP 포워딩과 명시적인 loopback 바인딩. iSCSI와의 조합은 별도의 합성 디스크 시험으로 검증했다.
- [Hitachi 동시 접근 설명](https://docs.hitachivantara.com/r/en-us/mk-92hnas006-33/block-level-access-through-iscsi/configuring-iscsi-logical-units/concurrent-access-to-logical-units): 일반 NTFS 볼륨에 대한 독립적인 동시 마운트의 충돌.
- [usbip-win](https://github.com/cezanne/usbip-win), [usbipd-win](https://github.com/dorssel/usbipd-win): 수신/송신 방향과 설치 제약.
- [Paragon 8.5 설명서](https://download.paragon-software.com/doc/Paragon_NTFS-HFS_for_Linux_8.5_User_Manual.pdf): 2011년 설명서의 인쇄 쪽50/PDF 쪽55. 오래된 명령 설명을 현재 Pi 지원 근거로 사용하지 않는다.
- [최신 Linux NTFS 드라이버 문서](https://www.kernel.org/doc/html/next/filesystems/ntfs.html): 압축 속성의 `chattr` 변경 미지원.
