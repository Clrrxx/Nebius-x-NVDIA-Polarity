# Running a bench on a Raspberry Pi 5 or NVIDIA Jetson Orin Nano (P2 notes)

The same code runs on Linux on ARM. These notes have not been tested on hardware yet (TODO-TEAM if you try it).

## Raspberry Pi 5 (8 GB), Raspberry Pi OS Bookworm (64-bit)

Bookworm ships Python 3.11, which is supported.

```bash
sudo apt update && sudo apt install -y python3-venv libgl1 libglib2.0-0 chromium-browser
git clone https://github.com/Clrrxx/Nebius-x-NVDIA-Submission.git polarity && cd polarity
scripts/setup_mac.sh            # the bash setup script works on Linux too
python -m polarity devices      # find the USB camera index (V4L2, /dev/videoN)
```

`opencv-contrib-python` publishes aarch64 wheels, so no source build is needed. ArUco detection and the quality
metrics run at the 2 Hz chip rate comfortably. A USB webcam is easiest; the Pi camera module works if it is exposed
as a V4L2 device (`libcamera` + `v4l2loopback`).

## Jetson Orin Nano (JetPack 6, Ubuntu 22.04)

Ubuntu 22.04 ships Python 3.10, so install 3.11 first, for example from the deadsnakes PPA:

```bash
sudo add-apt-repository ppa:deadsnakes/ppa && sudo apt install -y python3.11 python3.11-venv libgl1
scripts/setup_mac.sh
```

The bench only does light edge vision; all model inference is in Token Factory, so CUDA is not required.

## Kiosk mode

```bash
CAMERA_INDEX=0 .venv/bin/python -m polarity run &
chromium-browser --kiosk --noerrdialogs --autoplay-policy=no-user-gesture-required http://127.0.0.1:8765/
```

To start on boot, add a systemd service (`ExecStart=/home/pi/polarity/.venv/bin/python -m polarity run`,
`WorkingDirectory=/home/pi/polarity`, `Restart=on-failure`) and launch Chromium from the desktop autostart. Use a USB
microphone and speaker for voice. Speech synthesis needs a voice installed (`sudo apt install speech-dispatcher
espeak-ng`).

## Hub mode on a class network

Run the TA laptop with `python -m polarity run --role hub --lan` and each bench with
`python -m polarity run --role bench --hub-url http://<hub-ip>:8765 --bench-id B07`. All machines must share the
same `TA_PIN`.
