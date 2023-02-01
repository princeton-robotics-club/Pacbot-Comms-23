# Robomodules

Robomodules is a python framework for developing systems that are composed of decoupled independently running modules that can communicate with each other through an asynchronous messaging system that runs on TCP traffic.

This repository holds the robomodules package. For example modules and a server, look at our [Robomodules-Examples repo](https://github.com/HarvardURC/Robomodules-Examples)

Robomodules is developed and maintained by the Harvard Undergraduate Robotics Club.

## Messaging system

The messaging system relies on messages, that are defined by the user using [Google's protocol buffers](https://developers.google.com/protocol-buffers/docs/pythontutorial). The user creates a protocol buffer and then associates it with a MsgType enum, which in turn get bassed to each of the modules and a central server. Each module connects to the server and can either send messages to the server or subscribe to specific message types. When the server receives a message from a module, it coolks up all of the modules that are connected to it and who have subscribed to that message type and forwards the message to those modules. Each module has a `msg_received` callback function, that gets called whenever the module receives a message. The `msg_received` callback has to parameters: `msg`, which holds the message in a de-serialized form (meaning that it is an object of the corresponding Protocol Buffer class) and `msg_type`, which holds the enum of the message type.

## Documentation

### robomodules.Server

To create a Robomodules server, just make an instance of this class, passing in the address and port where you want to run the server as well as the enum class of message types.

#### __init_\_(self, addr, port, MsgType)

- addr - The ip address of the server that is going to run.
- port - The port, that the server is going to run on.
- MsgType - The message type enum class, which holds the enums for all of your messages.

#### run(self)
This function starts the server.

#### quit(self)
This function stops the server.

### robomodules.ProtoModule
To create a Robomodules module, make a new module class that inherits from `robomodules.ProtoModule`. Your module has to call the super classes `__init__` function as well as implement the `tick` and `msg_received` functions.

####  __init_\_(self, addr, port, message_buffers, MsgType, frequency=0, subscriptions=[], loop=None)

- addr - The address of the server this module is going to connect to.
- port - The port of the server this module is going to connect to.
- message_buffers - message_buffers is a dictionary, where the keys are the various values of the MsgType enum class and the values are the corresponding protocol buffer message classes.
- frequency (default = `0`) - The frequency with which the classes tick function will get called. If missing or `0`, then tick won't get called automatically.
- subscriptions (default = `[]`) - List of initial message types that this module will subscribe to. If missing or `[]`, then no message types will be subscribed to.
- loop (default = None) - The asyncio event loop this module will run on. If None, then will create a new one.

#### tick(self)

If the frequency of the module is a positive non-zero value, then this function will automatically get called with a frequency of frequncy Hz. This is the main loop for the module.
Every module has to implement this function, even if it doesn't use it.

#### msg_received(self, msg, msg_type)

This function will get called whenever the module receives a message of a type that it has subscribed to. `msg` will contain the message as a protocol buffer object and msg_type will contain the message type as an enum from the `MsgType` enum class that the module was initialized with.
Every module has to implement this function, even if it doesn't use it.

#### subscribe(self, msg_types)

msg_types - a list of message types to subscribe to. The message types have to be values of the `MsgType` enum class.

#### unsubscribe(self, msg_types)

msg_types - a list of message types to unsubscribe from. The message types have to be values of the `MsgType` enum class.

#### set_frequency(self, frequency)

Sets the frequency (in Hz) with which the modules tick function gets called to frequency.

#### write(self, msg, msg_type)

This function will send the `msg` to the server, classyfing it as of type `msg_type`.
- msg - `msg` has to be serialized into a string. If dealing with a protocol buffer class, then you should call `buffer.SeriaToString()` before passing it in as the msg.
- msg_type - a value from the `MsgType` enum class.

#### connect(self)

Calling this function will connect the module to the server. If your code has multiple modules running on the same event loop, then you should connect all but one of them and call the `run()` method on the last one.

#### run(self)

This function starts the module.

#### quit(self)

This function stops the module.

## Writing robomodules modules

The example system consists of a simple message type, that contains a single int; a simple server; a simple "sensor" module, that sends a message to the server containing a random int; and a simple display module, that subscribes to our message type and periodically prints out the value that it received in the latest message. To demonstrate subscribing and unsubscribing functionality, the display module will also periodically unsubsribe and resubscribe to the message. All of the sample files can be found in our [Robomodules-Examples repo](https://github.com/HarvardURC/Robomodules-Examples).

### messages/mockMsg.proto

MockMsg.proto is the protocol buffer definition for our sample message, that contains just a single int. in order to keep a better structure, we have put this file in a separate directory/package called messages.

```
syntax = "proto2";

package rmExamples;

message MockMsg {

  required int32 mockValue = 1;
}
```

Once we've defined the structure of the buffer, we have to actually build it. For this we need to first install the Google protocol buffer python compiler (instructions [here](https://developers.google.com/protocol-buffers/docs/downloads)) and run the following command:
```protoc -I=./ --python_out=./ ./mockMsg.proto```

This will compile the `.proto` description into a python class called `mockMsg_pb2.py`.

### messages/__init_\_.py

in our `__init__.py` file we will create an enum that holds the message types and then associate the enum with the buffer that we just built. To create the association, we make a dictionary, where the keys are the enums and the values are the corresponding message classes. Finally we add the enum class (`MsgType`), the association (`message_buffers`) and the message class (`MockMsg`) to the `__all__` variable, so these would be imported if another scripts imports the messages package using `from messages import *`.

```
from enum import Enum
from .mockMsg_pb2 import MockMsg

class MsgType(Enum):
    MOCK_MSG = 0

message_buffers = {
    MsgType.MOCK_MSG: MockMsg
}


__all__ = ['MsgType', 'message_buffers', 'MockMsg']
```

### sampleServer.py

Our sample server will create a robomodules server on a given address and port, passing the `MsgType` enum class, so the server would be able to parse our messages and then run it. For convenience sake, we try to get the address and port from environment variables and if those aren't set, we default to localhost:11297.


```
#!/usr/bin/env python3

import robomodules
import os
from messages import MsgType

ADDRESS = os.environ.get("BIND_ADDRESS","localhost")
PORT = os.environ.get("BIND_PORT", 11297)

def main():
    server = robomodules.Server(ADDRESS, PORT, MsgType)
    server.run()

if __name__ == "__main__":
    main()
```

### mockSensorModule.py

```
#!/usr/bin/env python3

import os, random
import robomodules as rm
from messages import *

ADDRESS = os.environ.get("BIND_ADDRESS","localhost")
PORT = os.environ.get("BIND_PORT", 11297)

FREQUENCY = 2

class MockSensorModule(rm.ProtoModule):
    def __init__(self, addr, port):
        super().__init__(addr, port, message_buffers, MsgType, FREQUENCY)

    def msg_received(self, msg, msg_type):
        # This gets called whenever any message is received
        # This module only sends data, so we ignore incoming messages
        return

    def tick(self):
        # this function will get called in a loop with FREQUENCY frequency
        # for this mock module we will just send a random int
        msg = MockMsg()
        msg.mockValue = random.randint(1, 9)
        msg = msg.SerializeToString()
        self.write(msg, MsgType.MOCK_MSG)


def main():
    module = MockSensorModule(ADDRESS, PORT)
    module.run()

if __name__ == "__main__":
    main()
```

Let's go through this module and see what's going on.

```
#!/usr/bin/env python3
```

This makes the module executable with the python3 interpreter.

```
import os, random
import robomodules as rm
from messages import *
```

Just a bunch of imports. We import os, so we could get the address and port from environment variables. we import random, so we could generate random numbers. Finally we import robomodules and our messages.

```
ADDRESS = os.environ.get("BIND_ADDRESS","localhost")
PORT = os.environ.get("BIND_PORT", 11297)

FREQUENCY = 2
```

We get the Address and Port of our server from environment variables, defaulting to localhost:11297 if they aren't specified. Finally we set the frequency (2Hz), with which the modules tick function is going to get called.

```
class MockSensorModule(rm.ProtoModule):
    def __init__(self, addr, port):
        super().__init__(addr, port, message_buffers, MsgType, FREQUENCY)
```

We declare a new class for our module, which inherits from `rm.ProtoModule`. In the `__init__` function for this class, we call the `__init__` function of the parent class (`rmProtoModule`), passing in the address, port, message_buffers (this is the message_type - protocol buffer association), MsgType (or message type enum class) and the frequency.

```
def msg_received(self, msg, msg_type):
    # This gets called whenever any message is received
    # This module only sends data, so we ignore incoming messages
    return
```
Every module has to implement 2 functions: `msg_received` and `tick`. This is the first of them. This module is a sensor and as such won't receive any messages. However we still have to implement this function, so we just return.

```
def tick(self):
    # this function will get called in a loop with FREQUENCY frequency
    # for this mock module we will just send a random int
```

This is the second mandatory function. As mentioned in the comments, this function will get called with a frequency of 2Hz (twice a second).

```
msg = MockMsg()
msg.mockValue = random.randint(1, 9)
```

We create a new `MockMsg` buffer and set its value field to a random int between 1 and 9.

```
msg = msg.SerializeToString()
self.write(msg, MsgType.MOCK_MSG)
```

we serialize the buffer to a string and call the modules `write` function (this is inherited from `rm.ProtoModule`). We pass in the serialized msg and the message type. This will send the message to the server.


```
def main():
    module = MockSensorModule(ADDRESS, PORT)
    module.run()
```

we make a new instance of the `MockSensorModule` class and initialize it with the address and port we got earlier. Finally we run it, which will kick off the loop.

```
if __name__ == "__main__":
    main()
```
This is necessary to make the script easily executable.


### mockDisplayModule.py

```
#!/usr/bin/env python3

import os
import robomodules as rm
from messages import message_buffers, MsgType

ADDRESS = os.environ.get("BIND_ADDRESS","localhost")
PORT = os.environ.get("BIND_PORT", 11297)

FREQUENCY = 10

class MockDisplayModule(rm.ProtoModule):
    def __init__(self, addr, port):
        self.subscriptions = [MsgType.MOCK_MSG]
        super().__init__(addr, port, message_buffers, MsgType, FREQUENCY, self.subscriptions)
        self.value = -1
        self.sub_ticks = 0
        self.subbed = True

    def msg_received(self, msg, msg_type):
        # This gets called whenever any message is received
        if msg_type == MsgType.MOCK_MSG:
            self.value = msg.mockValue

    def tick(self):
        # this function will get called in a loop with FREQUENCY frequency
        # for this mock module we will print out the current value
        print('Current value: {}'.format(self.value))

        # to demonstrate subscription and unsubscription,
        # we will periodically unsubscribe and resubscribe
        if self.sub_ticks > 100:
            if self.subbed:
                print('Unsubscribed!')
                self.unsubscribe([MsgType.MOCK_MSG])
            else:
                print('Subscribed!')
                self.subscribe([MsgType.MOCK_MSG])
            self.subbed = not self.subbed
            self.sub_ticks = 0
        self.sub_ticks += 1


def main():
    module = MockDisplayModule(ADDRESS, PORT)
    module.run()

if __name__ == "__main__":
    main()

```
This module is quite similar to the previous module. Let's look at some of the differences:

```
def __init__(self, addr, port):
    self.subscriptions = [MsgType.MOCK_MSG]
    super().__init__(addr, port, message_buffers, MsgType, FREQUENCY, self.subscriptions)
    self.value = -1
    self.sub_ticks = 0
    self.subbed = True

```

This time we initialize the superclass with an initial list of subscriptions. Since this module will be displaying the value from `MOCK_MSG` messages, we will subscribe to that type. Finally, we keep track of the value most recently received. We initialize this value to -1. We also keep track of a sub_ticks value, which we will use to periodically subscribe and unsubscribe from the server. Finally we keep track of wheter or not we are currently subscribed.

```
def msg_received(self, msg, msg_type):
    # This gets called whenever any message is received
    if msg_type == MsgType.MOCK_MSG:
        self.value = msg.mockValue
```

This time we are receiving messages. We first check to make sure that the message is of the correct type and if it is, then we update our internal value with the value from the message.

```
def tick(self):
    # this function will get called in a loop with FREQUENCY frequency
    # for this mock module we will print out the current value
    print('Current value: {}'.format(self.value))
```
This time in our tick function we first just print out the value that we have stored internally.

```
# to demonstrate subscription and unsubscription,
# we will periodically unsubscribe and resubscribe
if self.sub_ticks > 100:
    if self.subbed:
        print('Unsubscribed!')
        self.unsubscribe([MsgType.MOCK_MSG])
    else:
        print('Subscribed!')
        self.subscribe([MsgType.MOCK_MSG])
    self.subbed = not self.subbed
    self.sub_ticks = 0
self.sub_ticks += 1
```
Fnally, if our `sub_ticks` counter has reached a certain limit, we unsubscribe from or resubscribe to the `MsgType.MOCK_MSG` messages.

## Running the modules and server.
To run the modules, first run the server and then run each of the modules separately. If a module crashes or is closed at any point, the rest of the system is going to be unaffected.
