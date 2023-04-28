#!/usr/bin/env python3
import os
import numpy as np
from robomodules import ProtoModule
from messages import MsgType, message_buffers, LightState, PacmanState
import serial
from Pacbot_High_Level.policies.high_level_policy import HighLevelPolicy
from Pacbot_High_Level.rl.grid import grid
from Pacbot_High_Level.rl.variables import o, O
from Pacbot_High_Level.constants import *
from messages import *

# Direction enums
right = 0
left = 1
up = 2
down = 3
# Grid enums
I = 1
o = 2
e = 3
O = 4
n = 5
c = 6

GAME_ENGINE_ADDRESS = os.environ.get("BIND_ADDRESS","10.9.28.246")
GAME_ENGINE_PORT = os.environ.get("BIND_PORT", 11297)

HARVARD_ENGINE_FREQUENCY = 24.0
GAME_ENGINE_FREQUENCY = 2.0*8*2

BLUETOOTH_MODULE_NAME = '/dev/cu.PURC_HC05_9'


GHOST_MOVES_WHILE_FRIGHTENED = 40
POWER_PELLET_VAL = 50

class GameEngineClient(ProtoModule):
    def __init__(self, addr, port, debug=False):

        # debug
        self.do_debug = debug


        self.subscriptions = [MsgType.LIGHT_STATE]
        self.debug("connecting to server.py...")
        super().__init__(addr, port, message_buffers, MsgType, GAME_ENGINE_FREQUENCY, self.subscriptions)
        self.debug("connected!")
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
        self.orientation = UP # current orientation which has been confirmed by a message from the robot
        self.loop.call_soon(self._frightened_timer)
        self.last_score = 0
        self.command_count = 1
        self.old_count = 1
        self.prev_pos = (14, 7) # starting coordinates
        self.life_count = 3


        # max # of squares to move threshold
        self.threshold = 5

        self.debug("connecting to bluetooth...")
        self.ser = serial.Serial(BLUETOOTH_MODULE_NAME, 115200, timeout=1)
        self.debug("connected!")


        # funky things
        self.cur_dir = left
        self.next_dir = left
        self.pacbot_starting_pos = [14, 7]
        self.pacbot_pos = [self.pacbot_starting_pos[0], self.pacbot_starting_pos[1]]

    def debug(self, msg: str):
        if self.do_debug:
            print(msg)


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
        if pac_pos in self.power_pellets and msg.score == self.last_score + POWER_PELLET_VAL:
            self.power_pellets.discard(pac_pos)
            self.frightened_timer = GHOST_MOVES_WHILE_FRIGHTENED

        # update last_score
        self.last_score = msg.score


    # convert int to bits of len=length (leading 0's)
    def get_bit_string(self, i: int, length):
        binary = str(bin(i))
        bits = str(binary).replace("0b","").zfill(length)
        return bits

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
        BOF = self.get_bit_string(int('0b01111100',2), 8) # ASCII: |
        EOF = self.get_bit_string(int('0b00001010',2), 8) # ASCII: \n

        # check for bad gamestate
        if self.state["game_state"] == 1:
            distance = 0

        # get count
        encoded_count = self.get_bit_string(self.command_count, 32)

        # get game state
        encoded_game_state = self.get_bit_string(self.state["game_state"], 8)

        # get action
        encoded_action,orientation = self._encode_action(action, target_distance=distance)

        command_arr = [BOF, encoded_count, encoded_game_state, encoded_action,  EOF]
        command_bin = "0b"
        for b in command_arr:
            command_bin = command_bin+(str(b).replace("0b", "").replace("x", ""))

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

        def get_bit_string(dist: int):
            binary = str(bin(dist))
            bits = str(binary).replace("0b","").zfill(5)
            return bits
        target_distance_bits = get_bit_string(target_distance)

        

        ACTION_MAPPING = [
            # Move forward
            '0{}11'.format(target_distance_bits), # FACE_UP    (west)  
            # '0{}10'.format(target_distance), # FACE_LEFT  (south)
            '1{}00'.format(target_distance_bits), # FACE_RIGHT (north) and go backward
            '0{}01'.format(target_distance_bits), # FACE_DOWN  (east)
            '0{}00'.format(target_distance_bits), # FACE_RIGHT (north)
            
            '10000001', # UP     #dummy 
            '10000001', # LEFT    
            '10000001', # DOWN   
            '1{}01'.format(target_distance_bits), # RIGHT    

            '00000011', # STAY go do distance 0
            '00000010', # STAY go do distance 0 #dummy command for the sake of modular
            '00000001', # STAY go do distance 0
            '00000000', # STAY go do distance 0
            
            '1{}01'.format(target_distance_bits), # FACE_DOWN  (east)  and go backward
            '1{}00'.format(target_distance_bits), # FACE_RIGHT (north) and go backward
            '1{}11'.format(target_distance_bits), # FACE_UP    (west)  and go backward
            '1{}10'.format(target_distance_bits), # FACE_LEFT  (south) and go backward
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

        orientation = action%4

        # forward or backward
        inverse_orientation_map = {0:2,1:3,2:0,3:1}
        # assume that 0 <= action <4
        if action < 4 and self.orientation == inverse_orientation_map[action % 4]: 
            action += 12
            orientation = self.orientation

        
        print('-' * 15)
        print("command action: " + ACTION_MAPPING_NAMES[action])
        self.debug("command action: " + ACTION_MAPPING[action])
        print("command distance: " + str(target_distance))
        print("facing: " + ACTION_MAPPING_NAMES[self.orientation + 4])
        self.debug("command count: " + str(self.command_count))

        ACTION_MAPPING_COMMANDS = [
            left, down, right, up
        ]

        # if action == STAY:
        #     self.next_dir = -1
        #     return
        
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


        # print("action  " + str(action))
        # print("orientation " + str(orientation))

    
        return ACTION_MAPPING[action] ,orientation
    
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
        def bitstring_to_bytes(s):
            v = int(s, 2)
            b = bytearray()
            i = 0
            while i < 8:
                b.append(v & 0xff)
                v >>= 8
                i += 1
            return bytes(b[::-1])
        byte_command = bitstring_to_bytes(encoded_cmd)
        self.ser.write(byte_command)

        
    def _read(self):
        # writes command over bluetooth
        msg = self.ser.read_until(expected=b'\n') # size is number of bytes
        self.ser.reset_input_buffer()
        print("received: " + str(msg))

        if len(msg) != 7:
            msg = self.ser.read_until(expected=b'\n')

        if len(msg) != 7:
            self.debug("error: dropped byte(s)!")
            self.debug("bad message received: " + str(msg))
            return (-1, False)
        
        if msg[6:7] != b'\n':
            self.debug(str(msg[6:7]))
            self.debug("error: eof missing")
            return (-1, False)
        if msg[0:1] != b'|':
            self.debug(str(msg[0:1]))
            self.debug("error: bof missing")
            return (-1, False)
        
        count = int.from_bytes(msg[1:5], "big")
        ack = True
        return (count, ack)
    
    def _read_ack(self, action, orientation):
        # read ack from robot (rotation ack)
        (count, ack) = self._read()
        self.debug("acknowledged num: " + str(count))

        if count > self.command_count:
            self.command_count = count

        if self.command_count == count and ack == True:
            # update orientation
            if FACE_UP <= action < STAY:
                self.orientation = orientation
            # move on to next command
            self._increment_count()

        # read ack from game engine (movement ack)
        if self.state["pac"][0] != self.prev_pos[0] or self.state["pac"][1] != self.prev_pos[1]:
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
            action, distance = self.policy.get_action(self.state)
            # if distance > 10:
            #     distance = 10
                
            # remove depreciated move commands
            if FACE_UP <= action < STAY:
                action -= 4
            
            # write commands
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
