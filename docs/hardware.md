# Hardware / 하드웨어

Reference configuration: Raspberry Pi 5 8GB, 64-bit Raspberry Pi OS, 7-inch Touch Display 2, Camera Module 3 Standard (IMX708), cooling and a suitable power supply. See [English assembly guide](../hardware/enclosure/README.md) / [한국어 조립 안내](../hardware/enclosure/README.ko.md).

기준 구성은 Pi 5 8GB, 7인치 Touch Display 2, Camera Module 3 Standard입니다. 디스플레이·카메라는 실제 CSI/DSI 포트와 OS 설정을 맞춥니다. 부트 설정을 다른 장치의 구성으로 무조건 덮어쓰지 않습니다. 공식 OS/EEPROM 업데이트 후 디스플레이와 카메라를 각각 확인합니다.

Use `rpicam-hello --list-cameras`, `wlr-randr`, backlight sysfs, and OS input-device tools to distinguish detection, compositor and physical-panel problems. A screenshot cannot prove panel brightness/flicker or physical touch accuracy. Server requests must not reset the local idle timer.

External partitions are identified by filesystem UUID and relative root paths. FAT32 has a 4 GiB per-file limit; recording is segmented. USB/NVMe throughput, cooling, camera field of view and print tolerances vary by hardware. A detected device alone is not a sustained-load test.
