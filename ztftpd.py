from ztftp.tftpd import TFTPd
import argparse

parser = argparse.ArgumentParser(description='Simple TFTP daemon')
parser.add_argument('-d', '--directory', default='/srv/tftp/',
                    help='Directory to serve via TFTP')
parser.add_argument('-i', '--interface', default='127.0.0.1',
                    help='Interface to listen on')
parser.add_argument('-p', '--port', default=69, help='UDP port to listen on')
args = parser.parse_args()

server = TFTPd(args.directory, args.interface, args.port)
server.run()
