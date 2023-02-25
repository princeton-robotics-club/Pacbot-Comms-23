
For ipUpdate to work correctly, first update the path to the ipUpdate file in the launcher.sh script.

In the terminal of your raspberry pi run the following commands

cd /
sudo crontab -e 

Then insert the following line into the bottom of the file

@reboot sh ${path_to_launcher.sh}/launcher.sh > ${path_to_logs}/cronlog 2>&1

replacing the paths with the actual paths

for example:

@reboot sh /home/purc1/Documents/Jack2bs/ipUpdate/launcher.sh > /home/purc1/logs/cronlog 2>&1

Save and exit. Reboot the pi and it should work.

Contact Jack if it doesn't.

This is not viable for future years since it uses my personal google account so ur gonna have to follow some tutorials on how to do this on your own if I'm not around. Here's what I used:

https://www.makeuseof.com/tag/read-write-google-sheets-python/