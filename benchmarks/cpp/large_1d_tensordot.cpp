// Copyright © 2026 Apple Inc.

#include <chrono>
#include <iomanip>
#include <iostream>
#include <string>
#include <vector>

#include "mlx/mlx.h"

namespace mx = mlx::core;

double milliseconds(std::chrono::high_resolution_clock::duration duration) {
  return std::chrono::duration_cast<std::chrono::nanoseconds>(duration).count() /
      1e6;
}

template <typename F>
double time_ms(F fn, int warmup, int iterations) {
  for (int i = 0; i < warmup; ++i) {
    mx::eval(fn());
  }

  auto start = std::chrono::high_resolution_clock::now();
  for (int i = 0; i < iterations; ++i) {
    mx::eval(fn());
  }
  auto end = std::chrono::high_resolution_clock::now();
  return milliseconds(end - start) / static_cast<double>(iterations);
}

int main(int argc, char** argv) {
  int iterations = 100;
  std::vector<int> sizes{32 * 4096 + 17, 64 * 4096, 256 * 4096};

  for (int i = 1; i < argc; ++i) {
    std::string arg(argv[i]);
    if (arg == "--iterations" && i + 1 < argc) {
      iterations = std::stoi(argv[++i]);
    }
  }

  std::cout << "size,prior_single_matmul_ms,optimized_tensordot_ms,speedup,"
               "prior_value,optimized_value"
            << std::endl;

  for (auto n : sizes) {
    auto a = mx::ones({n}, mx::float32, mx::Device::gpu);
    auto b = mx::full({n}, 2.0f, mx::float32, mx::Device::gpu);
    mx::eval(a, b);

    auto prior = [&]() {
      return mx::reshape(
          mx::matmul(
              mx::reshape(a, {1, n}, mx::Device::gpu),
              mx::reshape(b, {n, 1}, mx::Device::gpu),
              mx::Device::gpu),
          {},
          mx::Device::gpu);
    };
    auto optimized = [&]() {
      return mx::tensordot(a, b, std::vector<int>{0}, std::vector<int>{0}, mx::Device::gpu);
    };

    auto baseline_value = prior().item<float>();
    auto optimized_value = optimized().item<float>();

    auto baseline_ms = time_ms(prior, 10, iterations);
    auto optimized_ms = time_ms(optimized, 10, iterations);

    std::cout << n << "," << std::fixed << std::setprecision(6) << baseline_ms
              << "," << optimized_ms << "," << baseline_ms / optimized_ms
              << "," << baseline_value << "," << optimized_value << std::endl;
  }
}
