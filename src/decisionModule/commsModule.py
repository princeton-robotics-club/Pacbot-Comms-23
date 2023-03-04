#!/usr/bin/env python3

import os
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


# GAME_ENGINE_ADDRESS = os.environ.get("BIND_ADDRESS","localhost")
# GAME_ENGINE_PORT = os.environ.get("BIND_PORT", 11297)
# Use windows IP when connecting 
# GAME_ENGINE_ADDRESS = os.environ.get("BIND_ADDRESS","10.9.186.78") # Pie
GAME_ENGINE_ADDRESS = os.environ.get("BIND_ADDRESS","192.168.1.73")
GAME_ENGINE_PORT = os.environ.get("BIND_PORT", 11297)
GAME_ENGINE_FREQUENCY = 24.0


class GameEngineClient(ProtoModule):
    def __init__(self, addr, port):
        self.subscriptions = [MsgType.LIGHT_STATE]
        super().__init__(addr, port, message_buffers, MsgType, GAME_ENGINE_FREQUENCY, self.subscriptions)
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
        self.orientation = UP

        self.loop.call_soon(self._frightened_timer)

        self.last_score = 0

        self.command_count = 0

        self.ser = serial.Serial('/dev/cu.PURC_HC05_2', 115200, timeout=1)

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
            self.frightened_timer = 40  # TODO: gather all relevant constants

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
        encoded_game_state = bitstring.Bits(int=self.state["game_state"], length=32)
        # format(self.state['game_state'], '032b')

        # get action
        encoded_action = self._encode_action(action)

        command_arr = [BOF, encoded_count, encoded_game_state, encoded_action,  EOF]

        command = bitstring.Bits('').join(command_arr).bytes # needs to be written as bytes
        self.command_count += 1
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
    N   -   Distance to move
    """
    def _encode_action(self, action: int):

        ACTION_MAPPING = [
            bitstring.Bits('0b11000000'), # UP
            bitstring.Bits('0b11000000'), # LEFT
            bitstring.Bits('0b11000000'), # DOWN
            bitstring.Bits('0b11000000'), # RIGHT
            bitstring.Bits('0b01100011'), # FACE_UP
            bitstring.Bits('0b00100001'), # FACE_LEFT
            bitstring.Bits('0b01000010'), # FACE_DOWN
            bitstring.Bits('0b00000000'), # FACE_RIGHT
            # bitstring.Bits('0b'), # STAY
        ]

        # check we are facing the right way before moving
        if action <= RIGHT and action != self.orientation:
            # change action to a face action
            action += 4
            # TODO: send a movement command
            # TODO: if facing oposite direction turn that into a backwards motion (use %2)

        return ACTION_MAPPING[action]
    
    def _write(self, encoded_cmd):
        # writes command over bluetooth
        # TODO: handle bluetooth connection failure
        self.ser.write(encoded_cmd)


    def msg_received(self, msg, msg_type):
        if msg_type == MsgType.LIGHT_STATE:
            self._update_pellets(msg)
            self.prev_state = self.state
            self.state = self._parse_light(msg)

    def tick(self):
        if self.state:
            action = self.policy.get_action(self.state)
            # TODO: wait for this to be acknowledged first by robot before update
            if FACE_UP <= action < STAY:
                self.orientation = action - 4
            # send message
            encoded_cmd = self._encode_command(action)
            print(self.state)
            print(action)
            print(encoded_cmd)
            self._write(encoded_cmd)
            # possibly use CV position message as an ack


def main():

    # This module will connect to server and receive the game state
    game_engine_module = GameEngineClient(GAME_ENGINE_ADDRESS, GAME_ENGINE_PORT)

    try:
        game_engine_module.run()
    except KeyboardInterrupt:
        game_engine_module.ser.close()


if __name__ == "__main__":
    main()
