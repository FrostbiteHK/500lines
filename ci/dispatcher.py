import argparse
import os
import re
import socket
import SocketServer
import time
import threading

import helpers


class ThreadingTCPServer(SocketServer.ThreadingMixIn, SocketServer.TCPServer):
    runners = []
    dead = False

def serve():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host",
                        help="dispatcher's host, by default it uses localhost",
                        default="localhost",
                        action="store")
    parser.add_argument("--port",
                        help="dispatcher's port, by default it uses 8888",
                        default=8888,
                        action="store")
    args = parser.parse_args()

    # Create the server, binding to localhost on port 9999
    server = ThreadingTCPServer((args.host, int(args.port)), DispatcherHandler)
    # Create a thread to check the runner pool
    def runner_checker(server):
        #TODO:mention that we can do timeout based kills (if BUSY for too long
        # etc)
        while not server.dead:
            time.sleep(1)
            for runner in server.runners:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    s.connect((runner["host"], int(runner["port"])))
                    s.send("ping")
                    response = s.recv(1024)
                    s.close()
                    if response != "pong":
                        print 'killing'
                        server.runners.remove(runner)
                except socket.error as e:
                    print 'killing'
                    server.runners.remove(runner)
    t = threading.Thread(target=runner_checker, args=(server,))
    try:
        t.start()
        # Activate the server; this will keep running until you
        # interrupt the program with Ctrl-C
        server.serve_forever()
    except (KeyboardInterrupt, Exception):
        # if anything happens, kill the thread
        server.dead = True
        t.join()


class DispatcherHandler(SocketServer.BaseRequestHandler):
    """
    The RequestHandler class for our dispatcher.
    This will dispatch test runners against the incoming commit
    and handle their test results
    """

    command_re = re.compile(r"""(\w*)([:]*.*)""")
    last_communication = None
    REPO_FOLDER = "/Users/mdas/Code/500/repo"

    def handle(self):
        # self.request is the TCP socket connected to the client
        self.data = self.request.recv(1024).strip()
        command_groups = self.command_re.match(self.data)
        if not command_groups:
            self.request.sendall("Invalid command")
            return
        command = command_groups.group(1)
        if (command == "status"):
            print "in status"
            self.last_communication = time.time()
            self.request.sendall("OK")
        elif (command == "dispatch"):
            print "going to dispatch"
            commit_hash = command_groups.group(2)
            if not self.server.runners:
                self.request.sendall("No runners are registered")
            else:
                # The coordinator can trust us to dispatch the test
                #TODO: add ability to batch tests using manifests
                self.request.sendall("OK")
                self.dispatch_tests(commit_hash)
        elif (command == "register"):
            print "register"
            address = command_groups.group(2)
            host, port = re.findall(r":(\w*)", address)
            runner = {"host": host, "port":port}
            self.server.runners.append(runner)
            self.request.sendall("OK")
        elif (command == "results"):
            results = command_groups.group(2)
            commit_hash = re.findall(r":(\w*):.*", results)[0]
            if not os.path.exists("test_results"):
                os.makedirs("test_results")
            with open("test_results/%s" % commit_hash, "w") as f:
                data = self.data.split(":")[1:]
                data = "\n".join(data)
                f.write(data)
                f.close()
            self.request.sendall("OK")
        else:
            self.request.sendall("Invalid command")


    def dispatch_tests(self, commit_hash):
        # let the server know we're going to handle the request
        # TODO: if too many runners are busy for too long, 
        # we should alert the coordinator
        # TODO: usually we handle this more gracefully, instead of hard-stopping
        while True:
            print 'trying'
            for runner in self.server.runners:
                response = helpers.communicate(runner, "runtest:%s" % commit_hash)
                print 'got response:%s' % response
                if response == "OK":
                    return
            time.sleep(2)


if __name__ == "__main__":
    #TODO: use argparse to accept a new coordinator address
    serve()