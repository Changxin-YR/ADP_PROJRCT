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
import { RouteProp } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import { warehouseApi } from '../../api/warehouse';
import { WarehouseDocument } from '../../types';
import { colors, typography, spacing, borderRadius, layout } from '../../theme';
import { WarehouseStackParamList } from '../../navigation/WarehouseStack';

type StockInOutScreenProps = {
  navigation: NativeStackNavigationProp<WarehouseStackParamList, 'StockInOut'>;
  route: RouteProp<WarehouseStackParamList, 'StockInOut'>;
};

const StockInOutScreen: React.FC<StockInOutScreenProps> = ({ navigation }) => {
  const [receipts, setReceipts] = useState<WarehouseDocument[]>([]);
  const [issues, setIssues] = useState<WarehouseDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [tab, setTab] = useState<'in' | 'out'>('in');

  const fetchData = useCallback(async (refresh = false) => {
    try {
      if (refresh) setRefreshing(true);
      else setLoading(true);
      const [receiptData, issueData] = await Promise.all([
        warehouseApi.listReceipts(1, 20),
        warehouseApi.listIssues(1, 20),
      ]);
      setReceipts(receiptData.items);
      setIssues(issueData.items);
    } catch (err) {
      console.warn('Failed to load stock records', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const records = tab === 'in' ? receipts : issues;

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton}>
          <Ionicons name="arrow-back" size={24} color={colors.text} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>出入库记录</Text>
        <View style={{ width: 36 }} />
      </View>

      {/* Tabs */}
      <View style={styles.tabBar}>
        <TouchableOpacity
          style={[styles.tabItem, tab === 'in' && styles.tabItemActive]}
          onPress={() => setTab('in')}
        >
          <Text style={[styles.tabText, tab === 'in' && styles.tabTextActive]}>入库</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.tabItem, tab === 'out' && styles.tabItemActive]}
          onPress={() => setTab('out')}
        >
          <Text style={[styles.tabText, tab === 'out' && styles.tabTextActive]}>出库</Text>
        </TouchableOpacity>
      </View>

      {loading ? (
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={colors.primary} />
        </View>
      ) : (
        <FlatList
          data={records}
          keyExtractor={(item) => String(item.id)}
          contentContainerStyle={styles.listContent}
          showsVerticalScrollIndicator={false}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={() => fetchData(true)} tintColor={colors.primary} />
          }
          renderItem={({ item }) => (
            <View style={styles.recordItem}>
              <View style={[
                styles.typeIcon,
                { backgroundColor: tab === 'in' ? colors.success + '15' : colors.error + '15' },
              ]}>
                <Ionicons
                  name={tab === 'in' ? 'arrow-down' : 'arrow-up'}
                  size={18}
                  color={tab === 'in' ? colors.success : colors.error}
                />
              </View>
              <View style={styles.recordContent}>
                <Text style={styles.recordMaterial}>{item.code}</Text>
                <Text style={styles.recordMeta}>
                  {item.created_at?.split('T')[0]} {item.name || ''}
                </Text>
              </View>
              <Text style={[styles.recordStatus, { color: tab === 'in' ? colors.success : colors.error }]}>
                {item.status === 'confirmed' ? '已确认' : item.status === 'verified' ? '已核验' : '待处理'}
              </Text>
            </View>
          )}
          ListEmptyComponent={
            <View style={styles.emptyContainer}>
              <Ionicons name="document-text-outline" size={48} color={colors.gray3} />
              <Text style={styles.emptyText}>暂无{tab === 'in' ? '入库' : '出库'}记录</Text>
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
  tabBar: {
    flexDirection: 'row',
    marginHorizontal: layout.screenPadding,
    marginVertical: spacing.md,
    backgroundColor: colors.backgroundSecondary,
    borderRadius: borderRadius.md,
    padding: 2,
  },
  tabItem: {
    flex: 1,
    paddingVertical: spacing.sm,
    borderRadius: borderRadius.md - 2,
    alignItems: 'center',
  },
  tabItemActive: {
    backgroundColor: colors.background,
  },
  tabText: {
    ...typography.subhead,
    color: colors.textTertiary,
    fontWeight: '500',
  },
  tabTextActive: {
    color: colors.primary,
    fontWeight: '600',
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  listContent: {
    padding: layout.screenPadding,
  },
  recordItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.separatorLight,
  },
  typeIcon: {
    width: 36,
    height: 36,
    borderRadius: borderRadius.md,
    justifyContent: 'center',
    alignItems: 'center',
  },
  recordContent: {
    flex: 1,
    marginLeft: spacing.md,
  },
  recordMaterial: {
    ...typography.body,
    color: colors.text,
    fontWeight: '500',
  },
  recordMeta: {
    ...typography.caption1,
    color: colors.textTertiary,
    marginTop: 2,
  },
  recordStatus: {
    ...typography.caption1,
    fontWeight: '600',
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

export default StockInOutScreen;
