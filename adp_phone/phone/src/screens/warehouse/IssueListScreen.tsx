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
import { Badge } from '../../components/common/Badge';
import { SearchBar } from '../../components/common/SearchBar';
import { warehouseApi } from '../../api/warehouse';
import { WarehouseDocument } from '../../types';
import { colors, typography, spacing, borderRadius, shadows, layout } from '../../theme';

type IssueListScreenProps = {
  navigation: NativeStackNavigationProp<any>;
};

const statusConfig: Record<string, { label: string; color: string }> = {
  draft: { label: '草稿', color: '#8E8E93' },
  submitted: { label: '已提交', color: '#FF9500' },
  verified: { label: '已核验', color: '#007AFF' },
  confirmed: { label: '已确认', color: '#34C759' },
};

const IssueListScreen: React.FC<IssueListScreenProps> = ({ navigation }) => {
  const [search, setSearch] = useState('');
  const [issues, setIssues] = useState<WarehouseDocument[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);

  const fetchIssues = useCallback(async (pageNum = 1, refresh = false) => {
    try {
      if (refresh) setRefreshing(true);
      else if (pageNum === 1) setLoading(true);
      const data = await warehouseApi.listIssues(pageNum, 20);
      if (refresh || pageNum === 1) {
        setIssues(data.items);
      } else {
        setIssues((prev) => [...prev, ...data.items]);
      }
      setHasMore(pageNum < data.pages);
      setPage(pageNum);
    } catch (err) {
      console.warn('Failed to load issues', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchIssues(1);
  }, [fetchIssues]);

  const filtered = issues.filter(
    (i) => (i.code || '').toLowerCase().includes(search.toLowerCase()) ||
           (i.name || '').toLowerCase().includes(search.toLowerCase())
  );

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={24} color={colors.text} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>出库单</Text>
        <TouchableOpacity style={styles.addBtn}>
          <Ionicons name="add" size={24} color={colors.primary} />
        </TouchableOpacity>
      </View>
      <View style={styles.searchContainer}>
        <SearchBar value={search} onChangeText={setSearch} placeholder="搜索出库单..." />
      </View>
      {loading && issues.length === 0 ? (
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={colors.primary} />
        </View>
      ) : (
        <FlatList
          data={filtered}
          keyExtractor={(item) => String(item.id)}
          renderItem={({ item }) => {
            const status = statusConfig[item.status] || statusConfig.draft;
            return (
              <TouchableOpacity style={styles.issueCard} activeOpacity={0.7}>
                <View style={styles.issueHeader}>
                  <Text style={styles.issueCode}>{item.code}</Text>
                  <Badge label={status.label} color={status.color} />
                </View>
                <Text style={styles.purpose}>{item.name || '-'}</Text>
                <View style={styles.issueFooter}>
                  <Text style={styles.issueMeta}>{item.created_at?.split('T')[0]}</Text>
                </View>
              </TouchableOpacity>
            );
          }}
          contentContainerStyle={styles.listContent}
          showsVerticalScrollIndicator={false}
          onEndReached={() => {
            if (hasMore && !loading) fetchIssues(page + 1);
          }}
          onEndReachedThreshold={0.3}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={() => fetchIssues(1, true)} tintColor={colors.primary} />
          }
          ListEmptyComponent={
            <View style={styles.emptyContainer}>
              <Ionicons name="document-text-outline" size={48} color={colors.gray3} />
              <Text style={styles.emptyText}>暂无出库单</Text>
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
    backgroundColor: colors.backgroundSecondary,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: layout.screenPadding,
    paddingVertical: spacing.md,
  },
  backBtn: {
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
    marginLeft: spacing.md,
  },
  addBtn: {
    width: 36,
    height: 36,
    borderRadius: borderRadius.full,
    justifyContent: 'center',
    alignItems: 'center',
  },
  searchContainer: {
    paddingHorizontal: layout.screenPadding,
    marginBottom: spacing.md,
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  listContent: {
    padding: layout.screenPadding,
    paddingTop: 0,
  },
  issueCard: {
    backgroundColor: colors.background,
    borderRadius: borderRadius.lg,
    padding: spacing.base,
    marginBottom: spacing.md,
    ...shadows.sm,
  },
  issueHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.sm,
  },
  issueCode: {
    ...typography.headline,
    color: colors.text,
  },
  purpose: {
    ...typography.subhead,
    color: colors.textTertiary,
    marginBottom: spacing.md,
  },
  issueFooter: {
    paddingTop: spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.separatorLight,
  },
  issueMeta: {
    ...typography.caption1,
    color: colors.textTertiary,
  },
  emptyContainer: {
    alignItems: 'center',
    paddingTop: 80,
  },
  emptyText: {
    ...typography.body,
    color: colors.textTertiary,
    marginTop: spacing.md,
  },
});

export default IssueListScreen;
