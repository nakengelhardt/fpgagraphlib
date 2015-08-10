import re
import sys

def read_graph(f):
	d = {}
	for line in f:
		match = re.match("(\d+)\s(\d+)", line)
		if match:
			source = int(match.group(1))
			sink = int(match.group(2))
			if source not in d:
				d[source] = set()
			if sink not in d:
				d[sink] =  set()
			d[source].add(sink)
			d[sink].add(source)
	print(d)
	return d


def main():
	if len(sys.argv) < 2:
		print("Usage: {} graphfile".format(sys.argv[0]))
		return
	with open(sys.argv[1]) as f:
		read_graph(f)

if __name__ == "__main__":
	main()