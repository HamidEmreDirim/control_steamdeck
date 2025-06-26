#!/usr/bin/env python3
import serial
import threading

PORT = "/dev/ttyUSB0"    # sizin portunuz
BAUD = 9600            # LR02 ile ayarlı baud

def reader(ser):
    """Seri porttan geleni okuyup ekrana basar."""
    while True:
        try:
            line = ser.readline().decode('utf-8', errors='ignore').rstrip()
        except serial.SerialException:
            print("Seri port kapandı.")
            break
        if line:
            print(f"[RX] {line}")

def writer(ser):
    """Kullanıcı girdiğini LoRa üzerinden yollar."""
    while True:
        try:
            msg = input()  # ENTER’lı metin
        except EOFError:
            break
        ser.write((msg + "\r\n").encode('utf-8'))

def main():
    ser = serial.Serial(PORT, BAUD, timeout=1)
    print(f"*** {PORT} açıldı, {BAUD} baud ***\nGönderilecek metni yazıp ENTER’a basın.\n")

    t = threading.Thread(target=reader, args=(ser,), daemon=True)
    t.start()

    try:
        writer(ser)
    except KeyboardInterrupt:
        pass
    finally:
        ser.close()
        print("\nÇıkılıyor.")

if __name__ == "__main__":
    main()
