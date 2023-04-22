#define max(a,b) (((a) > (b)) ? (a) : (b))

#include <arpa/inet.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>
#include <fcntl.h>
#include <stdlib.h>
#include <errno.h>
#include <sys/time.h>
#include <sys/select.h>

#define GAME_ENGINE_PORT 11297
#define OFFBOARD_PORT 11296
#define GAME_ENGINE_IP "0.0.0.0"

int client_sock;
int offboard_sock;
int listener_sock;

int listen_for_offboard(int listener_socket)
{
    //fd_set read_set;
    //FD_ZERO(&read_set);
    //FD_SET(listener_socket, &read_set);

    int offboard_sock;
    offboard_sock = accept(listener_socket, NULL, NULL);
    printf("Listener sock made a connection!\n");

    // Set our offboard's socket to be nonblocking.
    int flags = fcntl(offboard_sock, F_GETFL);
    fcntl(offboard_sock, F_SETFL, flags | O_NONBLOCK);

    return offboard_sock;
}

int connect_to_gameEngine(void)
{
    // Our client's socket
    int client_sock;

    if ((client_sock = socket(AF_INET, SOCK_STREAM, 0)) < 0) {
        printf("\n Socket creation error \n");
        return -1;
    }
    printf("Client Socket created\n");

    // Set our client's socket to be nonblocking.
    int flags = fcntl(client_sock, F_GETFL);
    fcntl(client_sock, F_SETFL, flags | O_NONBLOCK);

    // Port and IP of gameEngine (the server)
    struct sockaddr_in sa_game_engine;
    sa_game_engine.sin_family = AF_INET;
    sa_game_engine.sin_port = htons(GAME_ENGINE_PORT);
    
    // This IP Address is for HARVARD'S GAMEENGINE
    if (inet_pton(AF_INET, GAME_ENGINE_IP, &sa_game_engine.sin_addr)
        <= 0) {
            printf("\nInvalid address/ Address not supported \n");
            return -1;
    }

    // Try connecting
    int connect_ret;
    connect_ret = connect(client_sock, (struct sockaddr*)&sa_game_engine, sizeof(sa_game_engine));
    if (connect_ret < 0)
    {
        // EINPROGRESS is okay, but any other error indicates a failure
        if (errno != EINPROGRESS){
            printf("\nConnection Failed %d\n", errno);
            return -1;
        }

        // This is updated by select() to indicate if a certain socket is writeable
        fd_set wfds;
        FD_ZERO(&wfds);             // Initializes wfds
        FD_SET(client_sock, &wfds); // Adds client_sock to wfds

        // Timeout for select call
        struct timeval tv;
        tv.tv_sec = 1;
        tv.tv_usec = 500;


        // Select will set client_sock in wfds if it is finished connecting
        // or connection failed
        select(client_sock+1, NULL, &wfds, NULL, &tv);
        if (!FD_ISSET(client_sock, &wfds))
        {
            // IN HERE COULD CHECK FOR DIFFERENT ERROR CODE (other than EINPROGRESS)
            // If Still EINPROGRESS, CAN MAYBE KEEP TRYING WITHOUT STARTING FUNCTION OVER AGAIN
            printf("Could not connect. Trying again\n");
            close(client_sock);
            return -1;
        }

        int error;
        int len = sizeof(error);
        // Portability issues here if using solaris and not berkeley!
        getsockopt(client_sock, SOL_SOCKET, SO_ERROR, &error, (socklen_t *) &len);
        if (error != 0)
        {
            printf("\nConnection Failed to game engine, is server.py running? %d\n", error);
            close(client_sock);
            return -1;
        }
    }
    printf("Connection made to GameEngine\n\n");
    return client_sock;
}


int main(int argc, char const* argv[])
{
    // Our client's socket
    int client_sock = -1;
    while((client_sock = connect_to_gameEngine()) == -1);

    int listener_socket;
    if ((listener_socket = socket(AF_INET, SOCK_STREAM, 0)) < 0) {
        printf("\n Socket creation error \n");
        exit(-1);
    }
    printf("Listener Socket created\n");

    // Set our Listener's socket to be nonblocking.
    //flags = fcntl(listener_socket, F_GETFL);
    //fcntl(listener_socket, F_SETFL, flags | O_NONBLOCK);


    struct sockaddr_in listener_addr;
    listener_addr.sin_family = AF_INET;
    listener_addr.sin_port = htons(OFFBOARD_PORT);
    if (inet_pton(AF_INET, "0.0.0.0", &listener_addr.sin_addr) <= 0)
    {
            printf("\nInvalid address/ Address not supported \n");
            exit(-1);
    }
    int bind_ret = bind(listener_socket, (struct sockaddr *)&listener_addr, sizeof(listener_addr));
    if (bind_ret < 0)
    {
        printf("Bind failed");
        exit(-1);
    }
    printf("Listener Socket bound\n");

    int listen_ret = listen(listener_socket, 10);
    if (listen_ret < 0)
    {
        printf("listen() failed");
        close(listener_socket);
        exit(-1);
    }
    printf("Listener Socket listening\n");

    int offboard_sock = listen_for_offboard(listener_socket);

    char client_buffer [1024];
    char offboard_buffer [1024];
    int client_buffer_size;
    int offboard_buffer_size;

    while (1)
    {
        int recv_ret = recv(client_sock, client_buffer, sizeof(client_buffer), 0);

        if (recv_ret < 0)
        {
            //printf("No data\n");
            if (errno != EWOULDBLOCK && errno != EAGAIN)
            {
                printf("Receive failed 1: errno %d\n", errno);
                close(offboard_sock);
                return -1;
            }
        }
        else if (recv_ret == 0)
        {
            printf("Connection to gameEngine closed\n");
            close(client_sock);
            while((client_sock = connect_to_gameEngine()) == -1);

            // Resend subscription request
            int send_ret = send(client_sock, offboard_buffer, offboard_buffer_size, 0);
            if (send_ret < 0)
            {
                printf("Send failed\n");
                close(client_sock);
                close(offboard_sock);
                return -1;
            }
            //close(offboard_sock);
            //return 0;
        }
        else
        {
            client_buffer_size = recv_ret;
            int send_ret = send(offboard_sock, client_buffer, client_buffer_size, 0);
            if (send_ret < 0)
            {
                printf("Send failed\n");
                close(client_sock);
                close(offboard_sock);
                return -1;
            }
            //printf("cbuf to offsock sent\n");
        }

        

        recv_ret = recv(offboard_sock, offboard_buffer, sizeof(offboard_buffer), 0);
        if (recv_ret < 0)
        {
            if (errno != EWOULDBLOCK && errno != EAGAIN)
            {
                if (errno == 104)
                {
                    printf("Connection to offboard closed\n");
                    close(offboard_sock);
                    offboard_sock = listen_for_offboard(listener_socket);
                }
                else
                {
                    printf("Receive failed 2\n");
                    close(client_sock);
                    return -1;
                }
            }
        }
        else if (recv_ret == 0)
        {
            printf("Connection to offboard closed\n");
            close(offboard_sock);
            //close(client_sock);
            //client_sock = connect_to_gameEngine();
            offboard_sock = listen_for_offboard(listener_socket);
            //close(client_sock);
            //close(offboard_sock);
            //printf("Ending Program\n");
            //return 0;
        }
        else
        {
            offboard_buffer_size = recv_ret;
            int send_ret = send(client_sock, offboard_buffer, offboard_buffer_size, 0);
            if (send_ret < 0)
            {
                printf("Send failed\n");

                close(client_sock);
                close(offboard_sock);
                return -1;
            }
            //printf("obuff to clisock sent\n");

        }
    }
}
