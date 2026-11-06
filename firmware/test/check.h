#pragma once

#include <stdio.h>

static int g_failures = 0;

#define CHECK(expr)                                                          \
  do {                                                                       \
    if (!(expr)) {                                                           \
      ++g_failures;                                                          \
      printf("%s:%d: CHECK failed: %s\n", __FILE__, __LINE__, #expr);        \
    }                                                                        \
  } while (0)

inline int checkSummary(const char* suite) {
  printf("%s: %s (%d failures)\n", suite, g_failures == 0 ? "PASS" : "FAIL", g_failures);
  return g_failures == 0 ? 0 : 1;
}
