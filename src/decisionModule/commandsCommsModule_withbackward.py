#!/usr/bin/env python3
import os
import time
import bitstring
import numpy as np
from robomodules import ProtoModule
from messages import MsgType, message_buffers, LightState, PacmanState
import serial
from Pacbot_High_Level.policies.high_level_policy import HighLevelPolicy
from Pacbot_High_Level.rl.grid import grid
from Pacbot_High_Level.rl.variables import o, O
from Pacbot_High_Level.constants import *
import pickle
import sys
from messages import *

# Direction enums
right = 0
left = 1
up = 2
down = 3
# Grid enums
# o = normal pellet, e = empty space, O = power pellet, c = cherry position
# I = wall, n = ghost chambers
I = 1
o = 2
e = 3
O = 4
n = 5
c = 6


# GAME_ENGINE_ADDRESS = os.environ.get("BIND_ADDRESS","localhost")
# GAME_ENGINE_PORT = os.environ.get("BIND_PORT", 11297)
# Use windows IP when connecting 
# GAME_ENGINE_ADDRESS = os.environ.get("BIND_ADDRESS","10.9.186.78") # Pie
GAME_ENGINE_ADDRESS = os.environ.get("BIND_ADDRESS","10.9.28.246")
GAME_ENGINE_PORT = os.environ.get("BIND_PORT", 11297)

HARVARD_ENGINE_FREQUENCY = 24.0
# GAME_ENGINE_FREQUENCY = 48.0
GAME_ENGINE_FREQUENCY = 2.0*8

BLUETOOTH_MODULE_NAME = '/dev/cu.PURC_HC05_9'


class GameEngineClient(ProtoModule):
    def __init__(self, addr, port, disable_bluetooth=False):
        self.subscriptions = [MsgType.LIGHT_STATE]
        print("connecting to server.py...")
        super().__init__(addr, port, message_buffers, MsgType, GAME_ENGINE_FREQUENCY, self.subscriptions)
        print("connected!")
        self.policy = HighLevelPolicy(debug=False)
        self.state = None

        self.power_pellets = {
            tuple(coord) for coord in np.argwhere(1 * (np.array(grid) == O)).tolist()
        }
        self.pellets = {
            tuple(coord) for coord in np.argwhere(1 * (np.array(grid) == o)).tolist()
        }
        # checks to override this timer
        self.frightened_timer = 0
        self.ticks_passed = 0
        self.orientation = UP #current orientation which has been confirmed by a message from the robot

        self.loop.call_soon(self._frightened_timer)

        self.last_score = 0

        self.command_count = 1
        self.old_count = 1

        self.prev_pos = (14, 7) #starting coordinates

        self.last_action = 8

        self.life_count = 3



        self.disable_bluetooth = disable_bluetooth
        if not disable_bluetooth:
            print("connecting to bluetooth...")
            self.ser = serial.Serial(BLUETOOTH_MODULE_NAME, 115200, timeout=1)
            print("connected!")



        # funky things
        self.cur_dir = left
        self.next_dir = left
        self.pacbot_starting_pos = [14, 7]
        self.pacbot_pos = [self.pacbot_starting_pos[0], self.pacbot_starting_pos[1]]

    def _frightened_timer(self):
        self.loop.call_later(1 / HARVARD_ENGINE_FREQUENCY, self._frightened_timer)
        self.ticks_passed += 1
        if self.ticks_passed % 12 == 0 and self.frightened_timer > 0:
            self.frightened_timer -= 1

    def _parse_light(self, msg: LightState):
        # check for life lost
        life_lost = False
        if msg.lives < self.life_count:
            self.life_count -= 1
            life_lost = True
            self.frightened_timer = 0

        # convert light state into dict
        return {
            "pellets": self.pellets,
            "power_pellets": self.power_pellets,
            "pac": (msg.pacman.x, msg.pacman.y),
            "r": (msg.red_ghost.x, msg.red_ghost.y),
            "b": (msg.blue_ghost.x, msg.blue_ghost.y),
            "o": (msg.orange_ghost.x, msg.orange_ghost.y),
            "p": (msg.pink_ghost.x, msg.pink_ghost.y),
            "rf": msg.red_ghost.state,
            "bf": msg.blue_ghost.state,
            "of": msg.orange_ghost.state,
            "pf": msg.pink_ghost.state,
            "score": msg.score,
            "dt": self.frightened_timer,
            "orientation": self.orientation,
            "game_state": msg.mode,
            "life_lost": life_lost,
        }


    def _reset_pellets(self):
        self.power_pellets = {
            tuple(coord) for coord in np.argwhere(1 * (np.array(grid) == O)).tolist()
        }
        self.pellets = {
            tuple(coord) for coord in np.argwhere(1 * (np.array(grid) == o)).tolist()
        }


    def _update_pellets(self, msg):

        # check for beginning of game and reset pellets
        if msg.score == 0:
            self._reset_pellets()

        pac_pos = (msg.pacman.x, msg.pacman.y)

        # update pellets (low score, so we are not too worried about validating if actually eaten)
        self.pellets.discard(pac_pos)

        # update power pellets
        # TODO: test this
        if pac_pos in self.power_pellets and msg.score == self.last_score + 50:
            self.power_pellets.discard(pac_pos)
            self.frightened_timer = 40  # TODO: gather all relevant constants?

        # update last_score
        self.last_score = msg.score

    """ _encode_command :
    takes in action and returns an encoded action in the following format

    Format :
    [ BOF C1 C2 C3 C4 GS A EOF ] (each is one byte)

    BOF -   Beginning of File ( | )
    C   -   Count (command number)
    GS  -   Game State (RUNNING=0, PAUSED=1)
    A   -   Action
    EOF -   End of File ( \n )

    """
    def _encode_command(self, action: int, distance : int):
        BOF = bin(int('0b01111100',2)) # ASCII: |
        EOF = bin(int('0b00001010',2)) # ASCII: \n

        # get count
        encoded_count = bitstring.Bits(int=self.command_count, length=32)
        # format(self.command_count, '032b')

        # get game state
        encoded_game_state = bitstring.Bits(int=self.state["game_state"], length=8)
        # format(self.state['game_state'], '032b')

        # get action
        print("target dist:" + str(distance))
        if self.state["game_state"] == 1:
            distance = 0
        # distance = 1
        print("target dist:" + str(distance))
        encoded_action,orientation = self._encode_action(action, target_distance=distance)

        command_arr = [BOF, encoded_count, encoded_game_state, encoded_action,  EOF]
        command_bin = "0b"
        for b in command_arr:
            command_bin = command_bin+(str(b).replace("0b", "").replace("x", ""))

            


        # command = bitstring.Bits('').join(command_arr).bytes # needs to be written as bytes
        print(command_bin)
        return command_bin,orientation


    """
    UP      ->  WEST
    LEFT    ->  SOUTH
    DOWN    ->  EAST
    RIGHT   ->  NORTH
    #former
    Action - Face (0) : Go Forward
    [ FB D1 D2 X X 0 D1 D2 ] (each is one bit)

    FB   -   Forward (0) Backward(1)
    D1  -   Direction 1 (N=00, S=01, E=10, W=11)
    D2  -   Direction 2 (N=00, S=01, E=10, W=11)
    X   -   Unused

    Action - Move (1) : Go 
    [ 1 FB N0 N1 N2 N3 N4 N5 ] (each is one bit)
    

    1   -   Move (1)
    FB  -   Forward (0) / Backward (1)
    N   -   Distance to move #this is either 0 or one now
    #current
    [ FB Dis1 Dis2 Dis3 Dis4 Dis5 Dir1 Dir2] 
    FB   -   Forward (0) Backward(1)
    Dir1  -   Direction 1 (N=00, S=01, E=10, W=11)
    Dir2  -   Direction 2 (N=00, S=01, E=10, W=11)
    """
    def _encode_action(self, action: int, target_direction: int = 0, target_distance: int = 1):#TO DO: get the information regarding distance to move

        """
        >>> "{0:b}".format(37)
        '100101'
        """

        def get_bit_string(dist: int):
            # print("target dist:" + str(dist))
            binary = str(bin(dist))
            bits = str(binary).zfill(5).replace("0b","")
            # bits = str(bin(dist))[2:]
            # return "0" * (5 - len(bits)) + bits
            return bits
        
        target_distance = get_bit_string(target_distance)
        # print("target dist out :" + str(target_distance))

        #For the time being. we assume that target_distance is either 0 or 1
        # ACTION_MAPPING = [
        #     # Move forward
        #     # bitstring.Bits('0b01100011'), # FACE_UP    (west)  
        #     # bitstring.Bits('0b01000010'), # FACE_LEFT  (south)
        #     # bitstring.Bits('0b00100001'), # FACE_DOWN  (east)
        #     # bitstring.Bits('0b00000000'), # FACE_RIGHT (north)
        #     bitstring.Bits('0b0{}11'.format(target_distance)), # FACE_UP    (west)  
        #     bitstring.Bits('0b0{}10'.format(target_distance)), # FACE_LEFT  (south)
        #     bitstring.Bits('0b0{}01'.format(target_distance)), # FACE_DOWN  (east)
        #     bitstring.Bits('0b0{}00'.format(target_distance)), # FACE_RIGHT (north)
            
        #     bitstring.Bits('0b10000001'), # UP     #dummy 
        #     bitstring.Bits('0b10000001'), # LEFT    
        #     bitstring.Bits('0b10000001'), # DOWN   
        #     bitstring.Bits('0b1{}01'.format(target_distance)), # RIGHT    

        #     bitstring.Bits('0b00000011'), # STAY go do distance 0
        #     bitstring.Bits('0b00000010'), # STAY go do distance 0 #dummy command for the sake of modular
        #     bitstring.Bits('0b00000001'), # STAY go do distance 0
        #     bitstring.Bits('0b00000000'), # STAY go do distance 0
            

        #     #go backward
        #     #bitstring.Bits('0b11000001'), # back  
        #     # move backward
        #     # bitstring.Bits('0b10100001'), # FACE_DOWN  (east)  and go backward
        #     # bitstring.Bits('0b10000000'), # FACE_RIGHT (north) and go backward
        #     # bitstring.Bits('0b11100011'), # FACE_UP    (west)  and go backward
        #     # bitstring.Bits('0b11000010'), # FACE_LEFT  (south) and go backward
        #     bitstring.Bits('0b1{}01'.format(target_distance)), # FACE_DOWN  (east)  and go backward
        #     bitstring.Bits('0b1{}00'.format(target_distance)), # FACE_RIGHT (north) and go backward
        #     bitstring.Bits('0b1{}11'.format(target_distance)), # FACE_UP    (west)  and go backward
        #     bitstring.Bits('0b1{}10'.format(target_distance)), # FACE_LEFT  (south) and go backward
        # ]      



        ACTION_MAPPING = [
            # Move forward
            # bitstring.Bits('0b01100011'), # FACE_UP    (west)  
            # bitstring.Bits('0b01000010'), # FACE_LEFT  (south)
            # bitstring.Bits('0b00100001'), # FACE_DOWN  (east)
            # bitstring.Bits('0b00000000'), # FACE_RIGHT (north)
            '0{}11'.format(target_distance), # FACE_UP    (west)  
            '0{}10'.format(target_distance), # FACE_LEFT  (south)
            '0{}01'.format(target_distance), # FACE_DOWN  (east)
            '0{}00'.format(target_distance), # FACE_RIGHT (north)
            
            '10000001', # UP     #dummy 
            '10000001', # LEFT    
            '10000001', # DOWN   
            '1{}01'.format(target_distance), # RIGHT    

            '00000011', # STAY go do distance 0
            '00000010', # STAY go do distance 0 #dummy command for the sake of modular
            '00000001', # STAY go do distance 0
            '00000000', # STAY go do distance 0
            

            #go backward
            #bitstring.Bits('0b11000001'), # back  
            # move backward
            # bitstring.Bits('0b10100001'), # FACE_DOWN  (east)  and go backward
            # bitstring.Bits('0b10000000'), # FACE_RIGHT (north) and go backward
            # bitstring.Bits('0b11100011'), # FACE_UP    (west)  and go backward
            # bitstring.Bits('0b11000010'), # FACE_LEFT  (south) and go backward
            '1{}01'.format(target_distance), # FACE_DOWN  (east)  and go backward
            '1{}00'.format(target_distance), # FACE_RIGHT (north) and go backward
            '1{}11'.format(target_distance), # FACE_UP    (west)  and go backward
            '1{}10'.format(target_distance), # FACE_LEFT  (south) and go backward
        ]      

        ACTION_MAPPING_NAMES = [
            # move forward
            "GO WEST",
            "GO SOUTH",
            "GO EAST",
            "GO NORTH",
            # turn
            "FACE WEST",#dummy
            "FACE SOUTH",
            "FACE EAST",
            "FACE NORTH",
            # stay  
            "STAY",
            "STAY",
            "STAY",
            "STAY",
            # go backward
            "GO BACK FACING EAST",
            "GO BACK FACING NORTH",
            "GO BACK FACING WEST",
            "GO BACK FACING SOUTH",
        ]   

        # UP = 0
        # LEFT = 1
        # DOWN = 2
        # RIGHT = 3
        # FACE_UP = 4
        # FACE_LEFT = 5
        # FACE_DOWN = 6
        # FACE_RIGHT = 7
        # STAY = 8
        # MOVE_TICKS = 6
        # TURN_TICKS = 36

        orientation = action%4

        #forward or backward
        inverse_orientation_map = {0:2,1:3,2:0,3:1}
        #assume that 0<=action <4
        if action <4 and self.orientation == inverse_orientation_map[action %4]: 
            action += 12
            orientation = self.orientation

        
        # if self.old_count != self.command_count:
            # self.old_count = self.command_count
        print('-' * 15)
        print("command action: " + ACTION_MAPPING_NAMES[action])
        print("command action: " + str(bin(int(ACTION_MAPPING[action],2))))
        print("facing: " + ACTION_MAPPING_NAMES[self.orientation + 4])
        print("command count: " + str(self.command_count))

        ACTION_MAPPING_COMMANDS = [
            left, down, right, up
        ]
        if action == STAY:
            self.next_dir = -1
            return
        
        self.next_dir = ACTION_MAPPING_COMMANDS[orientation]#not checked whether it 

        if self.state["game_state"] != 1:
            if not self._move_if_valid_dir(self.next_dir, self.state["pac"][0], self.state["pac"][1]):
                self._move_if_valid_dir(self.cur_dir, self.state["pac"][0], self.state["pac"][1])
        else:
            # reset pacbot position
            self.pacbot_pos = [self.pacbot_starting_pos[0], self.pacbot_starting_pos[1]]


        pos_buf = PacmanState.AgentState()
        pos_buf.x = self.pacbot_pos[0]
        pos_buf.y = self.pacbot_pos[1]
        pos_buf.direction = self.cur_dir
        # self.write(pos_buf.SerializeToString(), MsgType.PACMAN_LOCATION)
    
        return bin(int(ACTION_MAPPING[action],2)) ,orientation
    
    def _increment_count(self):
        # we want to avoid sending \n to robot
        self.command_count += 1
        count_in_16 =  np.base_repr(self.command_count,16)
        def avoid_A(count_in_16): # A corresponds to '\n'
            dict = {'0':'0','1':'1','2':'2','3':'3','4':'4','5':'5','6':'6','7':'7','8':'8','9':'9','A':'b','B':'b','C':'c','D':'d','E':'e','F':'f'}
            count_in_16 = [dict[i] for i in count_in_16]
            return "".join(count_in_16)
        count_in_16_withoutA = avoid_A(count_in_16)
        self.command_count = int(count_in_16_withoutA,16)
 
    def _write(self, encoded_cmd):
        # writes command over bluetooth
        # TODO: handle bluetooth connection failure
        self.ser.write(bytes(int(encoded_cmd,2)))

        
    def _read(self):
        # writes command over bluetooth
        # TODO: handle bluetooth connection failure
        msg = self.ser.read_until(expected=b'\n') # size is number of bytes
        self.ser.reset_input_buffer()
        # print(str(msg))

        if len(msg) != 7:
            msg = self.ser.read_until(expected=b'\n')

        if len(msg) != 7:
            # print("error: dropped byte(s)!")
            # print("bad message received: " + str(msg))
            return (-1, False)
        
        if msg[6:7] != b'\n':
            # print(str(msg[6:7]))
            # print("error: eof missing")
            return (-1, False)
        if msg[0:1] != b'|':
            # print(str(msg[0:1]))
            # print("error: bof missing")
            return (-1, False)
        
        count = int.from_bytes(msg[1:5], "big")
        ack = True
        return (count, ack)
    
    def _read_ack(self, action,orientation):
        # read ack from robot (rotation ack)
        (count, ack) = self._read()
        # print("command sent: " + str(self.command_count))
        # print("acknowledged num: " + str(count))

        if count > self.command_count:
            self.command_count = count


        if self.command_count == count and ack == True:
            # update orientation
            if FACE_UP <= action < STAY:
                self.orientation = orientation
            # move on to next command
            self._increment_count()

        
        # read ack from game engine (movement ack)
        if self.state["pac"][0] != self.prev_pos[0] and self.state["pac"][1] != self.prev_pos[1]:
            self.prev_pos = (self.state["pac"][0], self.state["pac"][1])
            self._increment_count()
            return
        
    
    def _move_if_valid_dir(self, direction, x, y):
        if direction == right and grid[x + 1][y] not in [I, n]:
            self.pacbot_pos[0] += 1
            self.cur_dir = direction
            return True
        elif direction == left and grid[x - 1][y] not in [I, n]:
            self.pacbot_pos[0] -= 1
            self.cur_dir = direction
            return True
        elif direction == up and grid[x][y + 1] not in [I, n]:
            self.pacbot_pos[1] += 1
            self.cur_dir = direction
            return True
        elif direction == down and grid[x][y - 1] not in [I, n]:
            self.pacbot_pos[1] -= 1
            self.cur_dir = direction
            return True
        return False


    def msg_received(self, msg, msg_type):
        if msg_type == MsgType.LIGHT_STATE:
            self._update_pellets(msg)
            self.prev_state = self.state
            self.state = self._parse_light(msg)

    def tick(self):
        if self.state:
            # action = self.last_action
            action, distance = self.policy.get_action(self.state)

            # TODO: wait for this to be acknowledged first by robot before update

            # TODO: Remove this temporary conversion from turning to actions. Put it somewhere better
            if FACE_UP <= action < STAY:#what does it do now?
                action -= 4

            # stop when game is paused
            # if self.state["game_state"] == 1:
            #     action = 8


             


            # if action > 3 and action <= 7:
            #     print(ACTION_MAPPING_COMMANDS[action - 4], end="\n")

            # if not 
            # send message
            encoded_cmd, orientation = self._encode_command(action, distance)

            self._write(encoded_cmd)
            # read acknowledgement message
            self._read_ack(action, orientation)

            



def main():

    # This module will connect to server and receive the game state
    game_engine_module = GameEngineClient(GAME_ENGINE_ADDRESS, GAME_ENGINE_PORT)

    try:
        game_engine_module.run()
    except KeyboardInterrupt:
        game_engine_module.ser.close()


if __name__ == "__main__":
    main()
