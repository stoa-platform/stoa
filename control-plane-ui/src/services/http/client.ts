import axios, { type AxiosInstance } from 'axios';
import { config } from '../../config';

export function createHttpInstance(): AxiosInstance {
  return axios.create({
    baseURL: config.api.baseUrl,
    // P1-2: default 30s — axios default is 0 (no timeout), leaving requests
    // hanging indefinitely when a backend pod stalls. Long-running endpoints
    // (e.g. /deploy) can override per-call via axios options { timeout: N }.
    timeout: config.api.timeout,
    headers: {
      'Content-Type': 'application/json',
    },
  });
}
