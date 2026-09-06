import React, { useState, useCallback, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  RefreshControl,
  ActivityIndicator,
} from 'react-native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import { colors, typography, spacing, borderRadius, layout } from '../../theme';
import { FeedingStackParamList } from '../../navigation/FeedingStack';
import { feedingApi } from '../../api/feeding';
import { FeedLog } from '../../types';

type FeedLogScreenProps = {
  navigation: NativeStackNavigationProp<FeedingStackParamList, 'FeedLog'>;
};

const FeedLogScreen: React.FC<FeedLogScreenProps> = ({ navigation }) => {
  const [logs, setLogs] = useState<FeedLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);

  const fetchLogs = useCallback(async (pageNum = 1, refresh = false) => {
    try {
      if (refresh) setRefreshing(true);
      else if (pageNum === 1) setLoading(true);
      const data = await feedingApi.listLogs(pageNum, 20);
      if (refresh || pageNum === 1) {
        setLogs(data.items);
      } else {
        setLogs((prev) => [...prev, ...data.items]);
      }
      setHasMore(pageNum < data.pages);
      setPage(pageNum);
    } catch (err) {
      console.warn('Failed to load feed logs', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchLogs(1);
  }, [fetchLogs]);

  const loadMore = () => {
    if (hasMore && !loading) {
      fetchLogs(page + 1);
    }
  };

  const formatTime = (dateStr: string) => {
    if (!dateStr) return '--';
    try {
      const d = new Date(dateStr);
      return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
    } catch {
      return dateStr;
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton}>
          <Ionicons name="arrow-back" size={24} color={colors.text} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>投喂记录</Text>
        <TouchableOpacity style={styles.addButton} onPress={() => navigation.navigate('FeedLogCreate')}>
          <Ionicons name="add" size={22} color={colors.primary} />
        </TouchableOpacity>
      </View>

      {loading && page === 1 ? (
        <ActivityIndicator size="large" color={colors.primary} style={{ marginTop: spacing.xl }} />
      ) : (
        <FlatList
          data={logs}
          keyExtractor={(item) => String(item.id)}
          contentContainerStyle={styles.listContent}
          showsVerticalScrollIndicator={false}
          onEndReached={loadMore}
          onEndReachedThreshold={0.3}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={() => fetchLogs(1, true)} tintColor={colors.primary} />
          }
          renderItem={({ item }) => (
            <View style={styles.logItem}>
              <View style={styles.logIcon}>
                <Ionicons name="nutrition" size={18} color={colors.warning} />
              </View>
              <View style={styles.logContent}>
                <Text style={styles.logPond}>{item.pond_name || `塘口 #${item.pond_id}`}</Text>
                <Text style={styles.logFeed}>{item.feed_name || item.feed_type || '饲料'} · {item.actual_amount || item.amount || 0}kg</Text>
                <Text style={styles.logMeta}>{formatTime(item.feed_time || item.created_at)} · {item.operator_name || '操作员'}</Text>
              </View>
              <Text style={styles.logAmount}>{item.actual_amount || item.amount || 0}kg</Text>
            </View>
          )}
          ListEmptyComponent={
            <View style={styles.emptyContainer}>
              <Ionicons name="nutrition-outline" size={48} color={colors.gray3} />
              <Text style={styles.emptyText}>暂无投喂记录</Text>
            </View>
          }
        />
      )}
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: layout.screenPadding,
    paddingVertical: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.separatorLight,
  },
  backButton: {
    width: 36,
    height: 36,
    borderRadius: borderRadius.full,
    justifyContent: 'center',
    alignItems: 'center',
  },
  headerTitle: {
    ...typography.headline,
    color: colors.text,
    flex: 1,
    textAlign: 'center',
  },
  addButton: {
    width: 36,
    height: 36,
    borderRadius: borderRadius.full,
    backgroundColor: colors.primary + '15',
    justifyContent: 'center',
    alignItems: 'center',
  },
  listContent: {
    padding: layout.screenPadding,
  },
  logItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.separatorLight,
  },
  logIcon: {
    width: 36,
    height: 36,
    borderRadius: borderRadius.md,
    backgroundColor: colors.warning + '10',
    justifyContent: 'center',
    alignItems: 'center',
  },
  logContent: {
    flex: 1,
    marginLeft: spacing.md,
  },
  logPond: {
    ...typography.body,
    color: colors.text,
    fontWeight: '500',
  },
  logFeed: {
    ...typography.subhead,
    color: colors.textTertiary,
    marginTop: 1,
  },
  logMeta: {
    ...typography.caption1,
    color: colors.gray2,
    marginTop: 2,
  },
  logAmount: {
    ...typography.headline,
    color: colors.text,
  },
  emptyContainer: {
    alignItems: 'center',
    paddingVertical: spacing.xxl,
  },
  emptyText: {
    ...typography.body,
    color: colors.textTertiary,
    marginTop: spacing.md,
  },
});

export default FeedLogScreen;
