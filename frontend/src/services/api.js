import axios from 'axios';
import { expireSession, isSessionExpired, touchActivity } from './session';

const api = axios.create({
  baseURL: 'http://localhost:8000',
  headers: {
    'Content-Type': 'application/json',
  },
});

api.interceptors.request.use((config) => {
  if (isSessionExpired()) {
    expireSession();
    return Promise.reject(new Error('Session expired'));
  }
  return config;
});

api.interceptors.response.use(
  (response) => {
    touchActivity();
    return response;
  },
  (error) => {
    if (error?.response?.status === 401) {
      expireSession();
    }
    return Promise.reject(error);
  }
);

export default api; 
