import axios, { type AxiosInstance } from 'axios';
import { config } from '../../config';

export function createHttpInstance(): AxiosInstance {
  return axios.create({
    baseURL: config.api.baseUrl,
    headers: {
      'Content-Type': 'application/json',
    },
  });
}
