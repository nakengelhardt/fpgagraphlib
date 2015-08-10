#include <stdint.h>
#define JUDYERROR_SAMPLE 1
#include "Judy.h"
#define MAXLINELEN 256           // define maximum string length

Pvoid_t PJSLArray = (Pvoid_t) NULL;  // initialize JudySL array

int last_node_id = 0;

int get_node(const uint8_t* key){
	Word_t* PValue;
	JSLI(PValue, PJSLArray, key);
	if (PValue == PJERR)            // if out of memory?
        {                               // so do something
            printf("Malloc failed -- get more ram\n");
            exit(1);
        }
	if(!*PValue){
		last_node_id++;
		printf("Creating node %s: internally %d\n", key, last_node_id);
		*PValue = (Word_t) last_node_id;
	}
	return (int) *PValue;
}

const uint8_t *testsequence[] = {"1", "2", "1", "3", "1", "4", "2"}; //, "5", "2", "6", "3", "4", "3", "7", "4", "5", "5", "6", "6", "7"};

int main(int argc, char const *argv[])
{
	for (int i = 0; i < sizeof(testsequence)/sizeof(testsequence[0]); ++i)
	{
		printf("%p\n", PJSLArray);
		get_node(testsequence[i]);
	}
	return 0;
}