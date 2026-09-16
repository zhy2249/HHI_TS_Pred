// Tiny standalone probe: tests TypeDef defaults without rebuilding the codec.
#include "TsFixedPrediction.h"
#include <cstdio>
int main()
{
  TsFixedPrediction::announce();
  std::printf("ACTUAL_MODE=%s\n", TsFixedPrediction::name());
  return 0;
}
