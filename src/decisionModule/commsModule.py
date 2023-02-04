#!/usr/bin/env python3

import os
import numpy as np
from robomodules import ProtoModule
from constants import UP, STAY, FACE_UP
from policies.high_level_policy import HighLevelPolicy
from rl.grid import grid
from rl.variables import o, O
from messages import MsgType, message_buffers, LightState, PacmanState




GAME_ENGINE_ADDRESS = os.environ.get("BIND_ADDRESS","localhost")
GAME_ENGINE_PORT = os.environ.get("BIND_PORT", 11297)
GAME_ENGINE_FREQUENCY = 0

class GameEngineClient(ProtoModule):
    def __init__(self, addr, port):
        self.subscriptions = [MsgType.LIGHT_STATE]
        super().__init__(addr, port, message_buffers, MsgType, GAME_ENGINE_FREQUENCY, self.subscriptions)
        self.policy = HighLevelPolicy()
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
    GS  -   Game State
    A   -   Action
    EOF -   End of File ( \n )

   
    """
    def _encode_command(self, action, game_state):
        BOF = b'01111100' # ASCII: |
        EOF = b'00001010' # ASCII: \n

        # get count
        encoded_count = format(self.command_count, '032b')

        # get game state
        encoded_game_state = 

        # get action
        encoded_action = self._encode_action(action)

        command_arr = [BOF, encoded_count, encoded_game_state, encoded_action,  EOF]



        
        command = b''.join(command_arr)
        self.command_count += 1
        return command


    """
    Action - Face (0) :
    [ 0 D1 D2 X X 0 D1 D2 ] (each is one bit)

    F   -   Face (0)
    D1  -   Direction 1 (N=00, S=01, E=10, W=11)
    D2  -   Direction 2 (N=00, S=01, E=10, W=11)
    X   -   Unused

    Action - Move (1) :
    [ 1 FB FB N0 N1 N2 N3 N4 N5 ] (each is one bit)

    1   -   Move (1)
    FB  -   Forward (0) / Backward (1)
    N   -   Distance to move
    """
    def _encode_action(self, action):

        return action

    def msg_received(self, msg, msg_type):
        if msg_type == MsgType.LIGHT_STATE:
            self._update_pellets(msg)
            self.state = self._parse_light(msg)

    def tick(self):
        if self.state:
            action = self.policy.get_action(self.state)
            if FACE_UP <= action < STAY:
                self.orientation = action - 4
            # TODO write message here
            # will probably be the bluetooth code here
            self.write()
            # possibly use CV position message as an ack


def main():

    # This module will connect to server and receive the game state
    game_engine_module = GameEngineClient(GAME_ENGINE_ADDRESS, GAME_ENGINE_PORT)
    game_engine_module.run()

if __name__ == "__main__":
    main()
