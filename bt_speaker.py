import subprocess
import time
import os

def setup_bluetooth():
    # Install necessary packages
    subprocess.run(["sudo", "apt-get", "update"])
    subprocess.run(["sudo", "apt-get", "install", "-y", "bluez", "pulseaudio", "pulseaudio-module-bluetooth"])

    # Add user to bluetooth group
    subprocess.run(["sudo", "usermod", "-a", "-G", "bluetooth", "pi"])

    # Set Bluetooth device name to R2D2
    subprocess.run(["sudo", "hciconfig", "hci0", "name", "R2D2"])

    # Make Pi discoverable
    subprocess.run(["sudo", "hciconfig", "hci0", "piscan"])

    # Start PulseAudio
    subprocess.Popen(["pulseaudio", "--start"])

    # Load Bluetooth module
    subprocess.run(["pactl", "load-module", "module-bluetooth-discover"])

def start_bluetooth_agent():
    # Start Bluetooth agent
    subprocess.Popen(["bluetoothctl", "agent", "NoInputNoOutput"])
    subprocess.Popen(["bluetoothctl", "default-agent"])

def main():
    print("Setting up Bluetooth...")
    setup_bluetooth()
    
    print("Starting Bluetooth agent...")
    start_bluetooth_agent()
    
    print("Raspberry Pi is now discoverable as 'R2D2' Bluetooth speaker.")
    print("You can now pair and connect your device.")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping Bluetooth speaker...")
        subprocess.run(["pulseaudio", "--kill"])

if __name__ == "__main__":
    main()
