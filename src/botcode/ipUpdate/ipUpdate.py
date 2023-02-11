from oauth2client.service_account import ServiceAccountCredentials
import gspread
import json
import socket
from datetime import datetime
import os
import time

start = time.time()

scopes = [
'https://www.googleapis.com/auth/spreadsheets',
'https://www.googleapis.com/auth/drive'
]

credentials = ServiceAccountCredentials.from_json_keyfile_name("raspberry-pi-ip-375618-cefcd46f10f8.json", scopes) #access the json key you downloaded earlier
file = gspread.authorize(credentials) # authenticate the JSON key with gspread
sheet = file.open("RaspberryPiIP") #open sheet
sheet = sheet.sheet1 #replace sheet_name with the name that corresponds to yours, e.g, it can be sheet1

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.connect(("8.8.8.8", 80))
IPAddr=s.getsockname()[0]

now = datetime.now()

sheet.update_acell('A1', IPAddr)
sheet.update_acell('B1', now.strftime("%H:%M:%S"))

end = time.time()

print("\n"+ str(end-start))