import pyuv
import signal
import time
import os
import struct
import time

def readstring(data):
    ''' Find newline, returns (string, remainder) tuple '''
    null = data.index('\x00')
    return data[:null], data[null+1:]


class TFTPd(object):
    def __init__(self, path='/tmp/tftp/', interface='0.0.0.0', port=69):
        self.interface = interface
        self.port = port
        if path.endswith('/'):
            self.path = path
        else:
            self.path = '{0}/'.format(path)
        if not os.path.isdir(self.path):
            raise Exception("{0} is not a directory".format(self.path))
        self.loop = pyuv.Loop.default_loop()
        self.shutdown_signal = pyuv.Signal(self.loop)
        self.timer = pyuv.Timer(self.loop)
        self.server = pyuv.UDP(self.loop)
        self.handles = [self.shutdown_signal, self.server, self.timer]
        self.state = {}
        self.operations = {'\x01': self.read_request,
                           '\x02': self.write_request,
                           '\x03': self.data_request,
                           '\x04': self.ack_request,
                           '\x05': self.error_request}

    def validate_path(self, filename):
        ''' This function interprets the filename and validates the path '''
        parsed = os.path.abspath(self.path + filename)
        if not parsed.startswith(self.path):
            # Something iffy was requested that resolved to file that's not in
            #  the configured directory
            msg = 'WARNING: User attempted to access file {0} via filename {1}'
            print msg.format(parsed, filename)
            return None
        return parsed

    def heartbeat(self, timer):
        ''' Check state on a heartbeat to ensure things are moving along '''
        # TODO: do something here!
        return

    def shutdown(self, handle, signum):
        ''' Cleans up handles on shutdown '''
        for handle in self.handles:
            handle.close()

    def send_error(self, address, code=0, message="Unexpected error occurred"):
        ''' Format a TFTP error and send '''
        error = '{0}{1}\x00'.format(struct.pack("!HH", 5, code), message)
        self.server.send(address, error)

    def send_data(self, address):
        ''' Sends the next block of data '''
        state = self.state[address]
        blockid = state['block'] + 1
        data = state['handle'].read(512)
        if len(data) < 512:
            self.state[address]['state'] = 'reading_final'
        msg = '{0}{1}'.format(struct.pack("!HH", 3, blockid), data)
        self.server.send(address, msg)

    def read_request(self, address, data):
        ''' Initiates TFTP read request handling '''
        filename, data = readstring(data)
        mode, data = readstring(data)
        filepath = self.validate_path(filename)
        msg = 'Client {0}:{1} requesting to read {2} ({3}) via {4} mode'
        print msg.format(address[0], address[1], filename, filepath, mode)
        if filepath is None:
            self.send_error(address, 2, "Invalid file path")
        elif not os.path.exists(filepath):
            self.send_error(address, 1, "File not found")
        else:
            filehandle = open(filepath, 'r')
            self.state[address] = {'state': 'reading',
                                   'file': filepath,
                                   'handle': filehandle,
                                   'block': 0}
            self.send_data(address)

    def write_request(self, address, data):
        ''' Initiates TFTP write request handling '''
        filename, data = readstring(data)
        mode, data = readstring(data)
        msg = 'Client {0}:{1} requesting to write {2} via {3} mode'
        print msg.format(address[0], address[1], filename, mode)
        self.send_error(address, 2, "Write requests not allowed by server")

    def data_request(self, address, data):
        ''' Handles inbound data associated with TFTP writes '''
        self.send_error(address, 5, "Unknown transfer ID")

    def ack_request(self, address, data):
        ''' Handles TFTP acknowledgement packets '''
        blockid = struct.unpack('!H', data)
        if address in self.state:
            state = self.state[address]
            if state['state'] == 'reading':
                state['block'] += 1
                self.send_data(address)
            elif state['state'] == 'reading_final':
                msg = "Read transfer of {0} to {1}:{2} complete"
                print msg.format(state['file'], address[0], address[1])
                del self.state[address]
        else:
            self.send_error(address, 5, "Unknown transfer ID")

    def error_request(self, address, data):
        ''' Handles inbound TFTP error packets '''
        print 'Client {0}:{1} sent error: {2}'.format(address[0], address[1],
                                                      repr(data))

    def inbound(self, handle, address, flags, data, error):
        ''' Reads inbound packets and routes requests to other methods '''
        if data is not None:
            opcode = data[1]
            if opcode not in self.operations:
                self.send_error(address, 4, "Unknown TFTP operation")
            else:
                try:
                    self.operations[opcode](address, data[2:])
                except Exception as exception:
                    print 'Error processing operation: {0}'.format(exception)
        else:
            print 'Communication error: {0}'.format(error)

    def run(self):
        print 'Starting zTFTPd, listening on {0}:{1}'.format(self.interface,
                                                             self.port)
        print 'Serving files from {0}'.format(self.path)
        self.shutdown_signal.start(self.shutdown, signal.SIGINT)
        self.server.bind((self.interface, self.port))
        self.server.start_recv(self.inbound)
        self.timer.start(self.heartbeat, 1, 1)
        self.loop.run()
