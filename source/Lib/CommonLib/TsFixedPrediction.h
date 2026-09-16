// Experimental out-of-band mode: encoder and decoder MUST use the same setting.
#pragma once
#include "CommonDef.h" // Loads TypeDef.h experiment defaults before testing macros.
#include <algorithm>
#include <cstdlib>
#include <cstring>
#include <cstdio>

namespace TsFixedPrediction
{
inline const char *defaultName()
{
#if JVET_BJUT_TS_FIXED_PREDICTOR && JVET_BJUT_TS_FIXED_NOPRED
  return "nopred";
#elif JVET_BJUT_TS_FIXED_PREDICTOR && JVET_BJUT_TS_FIXED_GRADIENT
  return "gradient";
#elif JVET_BJUT_TS_FIXED_PREDICTOR && JVET_BJUT_TS_FIXED_DIRECTIONAL
  return "directional";
#else
  return "current";
#endif
}
inline const char *name()
{
#if JVET_BJUT_TS_FIXED_PREDICTOR
  static const char *value = []() {
    const char *v = std::getenv("TS_FIXED_PREDICTOR");
    if (!v) { return defaultName(); }
    if (std::strcmp(v, "current") && std::strcmp(v, "nopred") &&
        std::strcmp(v, "gradient") && std::strcmp(v, "directional"))
    {
      std::fprintf(stderr, "Invalid TS_FIXED_PREDICTOR: %s\n", v);
      std::exit(EXIT_FAILURE);
    }
    return v;
  }();
  return value;
#else
  return "current";
#endif
}
inline int mode()
{
  static const int value = !std::strcmp(name(), "nopred") ? 0 :
                          !std::strcmp(name(), "gradient") ? 2 :
                          !std::strcmp(name(), "directional") ? 3 : 1;
  return value;
}
inline void announce()
{
#if JVET_BJUT_TS_FIXED_PREDICTOR
  std::printf("EXPERIMENT: TS_FIXED_PREDICTOR=%s; syntax=experimental-v1\n", name());
  std::printf("TS predictor default: %s; selection: %s\n", defaultName(),
              std::getenv("TS_FIXED_PREDICTOR") ? "environment override" : "TypeDef.h default");
#endif
}
// Magnitudes are bounded by codec transform dynamic range. Use wider arithmetic
// for extrapolation/edge scores; the returned predictor stays within [min,max].
inline int predict(int mode, int x, int y, int l, int u, int d, int ll, int uu)
{
  const int hi = std::max(l, u), lo = std::min(l, u);
  if (mode == 0) { return 0; }
  if (mode == 2 && x > 0 && y > 0)
  {
    return int(std::max<long long>(lo, std::min<long long>(hi, (long long)l + u - d)));
  }
  if (mode == 3 && x >= 2 && y >= 2)
  {
    const auto eh = std::abs((long long)l - ll) + std::abs((long long)u - d);
    const auto ev = std::abs((long long)u - uu) + std::abs((long long)l - d);
    return eh < ev ? l : ev < eh ? u : hi;
  }
  return hi;
}
}
