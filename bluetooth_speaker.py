import subprocess
import time
import os

def run_command(command):
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    output, error = process.communicate()
    if error:
        print(f"Error: {error.decode('utf-8')}")
    return output.decode('utf-8')

def setup_bluetooth():
    print("Updating package list...")
    run_command("sudo apt-get update")
    
    print("Installing necessary packages...")
    run_command("sudo apt-get install -y bluez pulseaudio pulseaudio-module-bluetooth")

    print("Setting Bluetooth device name to R2D2...")
    run_command("sudo hciconfig hci0 name 'R2D2'")

    print("Making Pi discoverable...")
    run_command("sudo hciconfig hci0 piscan")

    print("Configuring PulseAudio...")
    pulseaudio_config = """
    load-module module-bluetooth-policy
    load-module module-bluetooth-discover
    load-module module-switch-on-connect
    """
    with open('/home/wvfiv/.config/pulse/default.pa', 'a') as f:
        f.write(pulseaudio_config)

    print("Restarting PulseAudio...")
    run_command("pulseaudio -k")
    run_command("pulseaudio --start")

    print("Setting persistent Bluetooth name...")
    with open('/etc/machine-info', 'w') as f:
        f.write('PRETTY_HOSTNAME=R2D2\n')
    run_command("sudo service bluetooth restart")

def start_bluetooth_agent():
    print("Starting Bluetooth agent...")
    run_command("bluetoothctl agent on")
    run_command("bluetoothctl default-agent")

def main():
    print("Setting up Bluetooth...")
    setup_bluetooth()
    
    start_bluetooth_agent()
    
    print("Raspberry Pi should now be discoverable as 'R2D2' Bluetooth speaker.")
    print("You can now pair and connect your device.")
    
    print("Checking Bluetooth status:")
    print(run_command("hciconfig -a"))
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping Bluetooth speaker...")
        run_command("pulseaudio -k")

if __name__ == "__main__":
    main()
