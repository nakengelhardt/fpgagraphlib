/* -*- mode: C; mode: folding; fill-column: 70; -*- */
/* Copyright 2010,  Georgia Institute of Technology, USA. */
/* See COPYING for license. */
#include "compat.h"
#include <stdio.h>
#include <stdlib.h>
#include <errno.h>
#include <string.h>
#include <math.h>

#include <assert.h>

#include <alloca.h> /* Portable enough... */
#include <fcntl.h>
#include <unistd.h>

#if !defined(__MTA__)
#include <getopt.h>
#endif


#include "graph500.h"
#include "rmat.h"
#include "kronecker.h"
#include "verify.h"
#include "prng.h"
#include "xalloc.h"
#include "options.h"
#include "generator/splittable_mrg.h"
#include "generator/make_graph.h"

static int64_t nvtx_scale;

static struct packed_edge * restrict IJ;
static int64_t nedge;

static int64_t bfs_root[NBFS_max];

int
main (int argc, char **argv)
{
  int * restrict has_adj;
  int fd;
  int64_t desired_nedge;
  if (sizeof (int64_t) < 8) {
    fprintf (stderr, "No 64-bit support.\n");
    return EXIT_FAILURE;
  }

  if (argc > 1)
    get_options (argc, argv);

  nvtx_scale = 1L<<SCALE;

  init_random ();

  desired_nedge = nvtx_scale * edgefactor;
  /* Catch a few possible overflows. */
  assert (desired_nedge >= nvtx_scale);
  assert (desired_nedge >= edgefactor);


  if (VERBOSE) fprintf (stderr, "Generating edge list...");
  if (use_RMAT) {
    nedge = desired_nedge;
    IJ = xmalloc_large_ext (nedge * sizeof (*IJ));
    rmat_edgelist (IJ, nedge, SCALE, A, B, C);
  } else {
    make_graph(SCALE, desired_nedge, userseed, userseed, &nedge, (struct packed_edge**)(&IJ));
  }
  if (VERBOSE) fprintf (stderr, " done.\n");

  if (dumpname)
    fd = open (dumpname, O_WRONLY|O_CREAT|O_TRUNC, 0666);
  else
    fd = 1;

  if (fd < 0) {
    fprintf (stderr, "Cannot open output file : %s\n",
	     (dumpname? dumpname : "stdout"));
    return EXIT_FAILURE;
  }

  write (fd, IJ, 2 * nedge * sizeof (*IJ));

  int buflen = strlen(dumpname) + strlen(".graph") + 1;
  char * graphname = (char *) malloc(buflen * sizeof(char));
  snprintf(graphname, buflen, "%s.graph", dumpname);

  FILE * file = fopen(graphname, "w");
  if(!file){
      fprintf (stderr, "Cannot open output file : %s\n",
  	     (graphname? graphname : "stdout"));
      return EXIT_FAILURE;
  }

  for (int64_t k = 0; k < nedge; ++k) {
    const int64_t i = get_v0_from_edge(&IJ[k]);
    const int64_t j = get_v1_from_edge(&IJ[k]);
    if (i != j)
      fprintf(file, "%" PRId64 " %" PRId64 "\n", i+1, j+1);
  }

  fclose(file);
  //close (fd);
  free(graphname);



  return EXIT_SUCCESS;
}
