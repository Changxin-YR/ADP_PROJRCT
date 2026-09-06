import { useState, useEffect } from 'react';
import NetInfo from '@react-native-community/netinfo';
import { apiClient } from '../api/client';

export const useOffline = () => {
  const [isOnline, setIsOnline] = useState(true);
  const [queueSize, setQueueSize] = useState(0);

  useEffect(() => {
    const unsubscribe = NetInfo.addEventListener((state) => {
      const online = state.isConnected ?? true;
      setIsOnline(online);

      // Process queue when back online
      if (online) {
        apiClient.processOfflineQueue().then(() => {
          setQueueSize(apiClient.getOfflineQueueSize());
        });
      }
    });

    return () => unsubscribe();
  }, []);

  useEffect(() => {
    setQueueSize(apiClient.getOfflineQueueSize());
  }, []);

  return { isOnline, queueSize };
};

export default useOffline;
