#!/usr/bin/env python3

import os
import time
import bitstring
import numpy as np
from robomodules import ProtoModule
from messages import MsgType, message_buffers, LightState, PacmanState
import serial
# from Pacbot_High_Level.policies.high_level_policy import HighLevelPolicy
# from Pacbot_High_Level.rl.grid import grid
# from Pacbot_High_Level.rl.variables import o, O
# from Pacbot_High_Level.constants import *
import pickle
import grid


# GAME_ENGINE_ADDRESS = os.environ.get("BIND_ADDRESS","localhost")
# GAME_ENGINE_PORT = os.environ.get("BIND_PORT", 11297)
# Use windows IP when connecting 
# GAME_ENGINE_ADDRESS = os.environ.get("BIND_ADDRESS","10.9.186.78") # Pie
# GAME_ENGINE_ADDRESS = os.environ.get("BIND_ADDRESS","10.9.140.100")
GAME_ENGINE_ADDRESS = os.environ.get("BIND_ADDRESS","localhost")
GAME_ENGINE_PORT = os.environ.get("BIND_PORT", 11297)
# GAME_ENGINE_FREQUENCY = 24.0
GAME_ENGINE_FREQUENCY = 100.0
BLUETOOTH_MODULE_NAME = '/dev/cu.PURC_HC05_9'

UP = 0
LEFT = 1
DOWN = 2
RIGHT = 3
FACE_UP = 4
FACE_LEFT = 5
FACE_DOWN = 6
FACE_RIGHT = 7
STAY = 8


MOVE_TICKS = 6
TURN_TICKS = 36

# Grid enums
# o = normal pellet, e = empty space, O = power pellet, c = cherry position
# I = wall, n = ghost chambers
I = 1
o = 2
e = 3
O = 4
n = 5
c = 6

class GameEngineClient(ProtoModule):
    def __init__(self, addr, port):
        self.subscriptions = [MsgType.LIGHT_STATE]
        super().__init__(addr, port, message_buffers, MsgType, GAME_ENGINE_FREQUENCY, self.subscriptions)
        # self.policy = HighLevelPolicy(debug=False)
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

        self.prev_pos = (14, 7) #starting coordinates

        self.ser = serial.Serial(BLUETOOTH_MODULE_NAME, 115200, timeout=1)

    def _frightened_timer(self):
        self.loop.call_later(1 / GAME_ENGINE_FREQUENCY, self._frightened_timer)
        self.ticks_passed += 1
        if self.ticks_passed % 12 == 0 and self.frightened_timer > 0:
            self.frightened_timer -= 1

    def _parse_light(self, msg: LightState):
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
        }

    def _update_pellets(self, msg):

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
    def _encode_command(self, action: int):
        BOF = bitstring.Bits('0b01111100') # ASCII: |
        EOF = bitstring.Bits('0b00001010') # ASCII: \n

        # get count
        encoded_count = bitstring.Bits(int=self.command_count, length=32)
        # format(self.command_count, '032b')

        # get game state
        self.state["game_state"] = 0
        encoded_game_state = bitstring.Bits(int=self.state["game_state"], length=8)
        # format(self.state['game_state'], '032b')

        # get action
        encoded_action = self._encode_action(action)

        command_arr = [BOF, encoded_count, encoded_game_state, encoded_action,  EOF]

        command = bitstring.Bits('').join(command_arr).bytes # needs to be written as bytes
        return command


    """
    UP      ->  WEST
    LEFT    ->  SOUTH
    DOWN    ->  EAST
    RIGHT   ->  NORTH

    Action - Face (0) :
    [ 0 D1 D2 X X 0 D1 D2 ] (each is one bit)

    F   -   Face (0)
    D1  -   Direction 1 (N=00, S=01, E=10, W=11)
    D2  -   Direction 2 (N=00, S=01, E=10, W=11)
    X   -   Unused

    Action - Move (1) :
    [ 1 FB N0 N1 N2 N3 N4 N5 ] (each is one bit)

    1   -   Move (1)
    FB  -   Forward (0) / Backward (1)
    N   -   Distance to move #this is either 0 or one now
    """
    def _encode_action(self, action: int, target_direction: int = 0, target_distance: int = 1):#TO DO: get the information regarding distance to move
        #For the time being. we assume that target_distance is either 0 or 1
        ACTION_MAPPING = [
            #Move forward
            bitstring.Bits('0b10000001'), # UP     
            bitstring.Bits('0b10000001'), # LEFT    
            bitstring.Bits('0b10000001'), # DOWN   
            bitstring.Bits('0b10000001'), # RIGHT    

            # #Move backward
            # bitstring.Bits('0b11000001'), # UP       
            # bitstring.Bits('0b11000001'), # LEFT     
            # bitstring.Bits('0b11000001'), # DOWN     
            # bitstring.Bits('0b11000001'), # RIGHT  
              
            #turn around
            bitstring.Bits('0b00000000'), # FACE_UP      
            bitstring.Bits('0b00100001'), # FACE_LEFT   
            bitstring.Bits('0b01000010'), # FACE_DOWN   
            bitstring.Bits('0b01100011'), # FACE_RIGHT  
            
            bitstring.Bits('0b10000000'), # STAY go do distance 0
            

            #go backward
            bitstring.Bits('0b11000001'), # back  
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

        # check we are facing the right way before moving
        # move_backward_next = False
        # action_num = 0
        # if  action != MOVE_TICKS and action != TURN_TICKS:
        #     if action == STAY:
        #         action_num = 12
        #     else:
        #         target_direction = action%4  
        #         if (action <= 3):#move
        #             # assert ( target_direction == self.orientation)
        #             #we assume that if (action <= 3), target_direction == self.orientation always hold
        #             action_num = target_direction
        #         elif target_direction == self.orientation:#turn around ?-> no need to do that
        #             action_num = 12
        #         elif target_direction%2 == self.orientation%2:# turn around ? -> avoid it by going backward

        #             # else:
        #             action_num = 12
        #             move_backward_next = True
        #         else:#we need to face first, we discard the information of position??
        #             action_num = target_direction
                
        
        # if action <= RIGHT and action != self.orientation:
        #     # change action to a face action
        #     action += 4
        #     # TODO: send a movement command to robot
            
            
        #     # TODO: if facing oposite direction turn that into a backwards motion (use %2)
        # action_num = 4
        return ACTION_MAPPING[action]
    
    def _increment_count(self):
        # we want to avoid sending \n to robot
        self.command_count+= 1
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
        print("sent command: " + str(encoded_cmd))
        self.ser.write(encoded_cmd)

        
    def _read(self):
        # writes command over bluetooth
        # TODO: handle bluetooth connection failure
        msg = self.ser.read_until(expected=b'\n') # size is number of bytes
        self.ser.reset_input_buffer()
        print("received ack: " + str(msg))

        if len(msg) != 7:
            msg = self.ser.read_until(expected=b'\n')

        if len(msg) != 7:
            print("error: dropped byte(s)!")
            print("bad message received: " + str(msg))
            return (-1, False)
        
        if msg[6:7] != b'\n':
            print(str(msg[6:7]))
            print("error: eof missing")
            return (-1, False)
        if msg[0:1] != b'|':
            print(str(msg[0:1]))
            print("error: bof missing")
            return (-1, False)
        
        count = int.from_bytes(msg[1:5], "big")
        ack = True #msg[5:6] == b'\x01'
        # if not ack:
        #     print(msg[5:6])
        return (count, ack)
    
    def _read_ack(self, action):
        # read ack from robot (rotation ack)
        (count, ack) = self._read()
        if count > self.command_count:
            self.command_count = count
        print(count, ack)
        print("self.command_count: " + str(self.command_count))
        if self.command_count == count and ack == True:
            # update orientation
            if FACE_UP <= action < STAY:
                self.orientation = action - 4
            # move on to next command
            self._increment_count()

        
        # read ack from game engine (movement ack)
        if self.state["pac"][0] != self.prev_pos[0] and self.state["pac"][1] != self.prev_pos[1]:
            self.prev_pos = (self.state["pac"][0], self.state["pac"][1])
            self._increment_count()
            return



    def msg_received(self, msg, msg_type):
        if msg_type == MsgType.LIGHT_STATE:
            self._update_pellets(msg)
            self.prev_state = self.state
            self.state = self._parse_light(msg)

    def keypress(self):
        char = input('command: ')

        self.command_count += 1
        if char == 'a':
            return FACE_RIGHT
        elif char == 'd':
            return FACE_LEFT
        elif char == 'w':
            return FACE_UP
        elif char == 's':
            return FACE_DOWN
        elif char == ' ':
            return UP
        elif char == 'b':
            return 9

    def tick(self):
        if self.state:

                # UP = 0
                # LEFT = 1
                # DOWN = 2
                # RIGHT = 3
                # FACE_UP = 4
                # FACE_LEFT = 5
                # FACE_DOWN = 6
                # FACE_RIGHT = 7
                # STAY = 8


            # action = self.policy.get_action(self.state)
            # TODO: wait for this to be acknowledged first by robot before update
            action = self.keypress()
            


            # check key presses
            # no key press -> no message
        
            # send message
            encoded_cmd = self._encode_command(action)
            self._write(encoded_cmd)

            # read acknowledgement message
            self._read_ack(action)


def main():

    # This module will connect to server and receive the game state
    game_engine_module = GameEngineClient(GAME_ENGINE_ADDRESS, GAME_ENGINE_PORT)

    try:
        game_engine_module.run()
    except KeyboardInterrupt:
        game_engine_module.ser.close()


if __name__ == "__main__":
    main()
    

# #
#     def keypress(self):
#         char = input('direction: ')
#         if char == 'a':
#             self.next_dir = PacmanCommand.WEST
#         elif char == 'd':
#             self.next_dir = PacmanCommand.EAST
#         elif char == 'w':
#             self.next_dir = PacmanCommand.NORTH
#         elif char == 's':
#             self.next_dir = PacmanCommand.SOUTH
#         elif char == 'q':
#             self.quit()
