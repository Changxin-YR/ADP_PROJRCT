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
import { Card } from '../../components';
import { Badge } from '../../components/common/Badge';
import { purchaseApi } from '../../api/purchase';
import { colors, typography, spacing, borderRadius, shadows, layout } from '../../theme';

interface Supplier {
  id: number;
  name: string;
  contact?: string;
  phone?: string;
  address?: string;
  status?: string;
  total_purchased?: number;
  total_paid?: number;
  balance?: number;
}

type Props = {
  navigation: NativeStackNavigationProp<any>;
};

const SupplierScreen: React.FC<Props> = ({ navigation }) => {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);

  const fetchData = useCallback(async (pageNum = 1, refresh = false) => {
    try {
      if (refresh) setRefreshing(true);
      else if (pageNum === 1) setLoading(true);
      const data = await purchaseApi.listSuppliers(pageNum, 20);
      if (refresh || pageNum === 1) {
        setSuppliers(data.items);
      } else {
        setSuppliers((prev) => [...prev, ...data.items]);
      }
      setHasMore(pageNum < data.pages);
      setPage(pageNum);
    } catch (err) {
      console.warn('Failed to load suppliers', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchData(1);
  }, [fetchData]);

  const loadMore = () => {
    if (hasMore && !loading) fetchData(page + 1);
  };

  const getStatusBadge = (status?: string) => {
    switch (status) {
      case 'active': return { label: '合作中', color: '#34C759' };
      case 'suspended': return { label: '暂停', color: '#FF9500' };
      case 'terminated': return { label: '已终止', color: '#8E8E93' };
      default: return { label: '合作中', color: '#34C759' };
    }
  };

  const renderItem = ({ item }: { item: Supplier }) => {
    const badge = getStatusBadge(item.status);
    return (
      <Card style={styles.card}>
        <View style={styles.cardHeader}>
          <View style={styles.avatarWrap}>
            <Ionicons name="business" size={20} color="#007AFF" />
          </View>
          <View style={styles.cardHeaderText}>
            <Text style={styles.nameText}>{item.name}</Text>
            {item.contact && <Text style={styles.contactText}>{item.contact}{item.phone ? ` · ${item.phone}` : ''}</Text>}
          </View>
          <Badge label={badge.label} color={badge.color} />
        </View>
        {(item.total_purchased != null || item.balance != null) && (
          <View style={styles.statsRow}>
            <View style={styles.statItem}>
              <Text style={styles.statValue}>¥{(item.total_purchased || 0).toLocaleString()}</Text>
              <Text style={styles.statLabel}>累计采购</Text>
            </View>
            <View style={styles.statItem}>
              <Text style={styles.statValue}>¥{(item.total_paid || 0).toLocaleString()}</Text>
              <Text style={styles.statLabel}>累计付款</Text>
            </View>
            <View style={styles.statItem}>
              <Text style={[styles.statValue, (item.balance || 0) > 0 && { color: colors.error }]}>
                ¥{(item.balance || 0).toLocaleString()}
              </Text>
              <Text style={styles.statLabel}>应付余额</Text>
            </View>
          </View>
        )}
      </Card>
    );
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={24} color={colors.text} />
        </TouchableOpacity>
        <Text style={styles.title}>供应商档案</Text>
        <TouchableOpacity style={styles.addBtn}>
          <Ionicons name="add" size={24} color={colors.textInverse} />
        </TouchableOpacity>
      </View>

      {loading && suppliers.length === 0 ? (
        <ActivityIndicator size="large" color={colors.primary} style={{ marginTop: spacing.xl }} />
      ) : (
        <FlatList
          data={suppliers}
          keyExtractor={(item) => String(item.id)}
          renderItem={renderItem}
          contentContainerStyle={styles.listContent}
          showsVerticalScrollIndicator={false}
          onEndReached={loadMore}
          onEndReachedThreshold={0.3}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={() => fetchData(1, true)} tintColor={colors.primary} />
          }
          ListEmptyComponent={
            <View style={styles.emptyContainer}>
              <Ionicons name="business-outline" size={48} color={colors.gray3} />
              <Text style={styles.emptyText}>暂无供应商</Text>
            </View>
          }
        />
      )}
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.backgroundSecondary },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: layout.screenPadding, paddingVertical: spacing.base },
  backBtn: { width: 36, height: 36, borderRadius: borderRadius.full, justifyContent: 'center', alignItems: 'center' },
  title: { ...typography.headline, color: colors.text, flex: 1, textAlign: 'center' },
  addBtn: { width: 36, height: 36, borderRadius: borderRadius.full, backgroundColor: colors.primary, justifyContent: 'center', alignItems: 'center', ...shadows.sm },
  listContent: { padding: layout.screenPadding, paddingTop: 0 },
  card: { marginBottom: spacing.md, padding: spacing.base },
  cardHeader: { flexDirection: 'row', alignItems: 'center', marginBottom: spacing.sm },
  avatarWrap: { width: 40, height: 40, borderRadius: borderRadius.md, backgroundColor: '#007AFF15', justifyContent: 'center', alignItems: 'center', marginRight: spacing.md },
  cardHeaderText: { flex: 1 },
  nameText: { ...typography.headline, color: colors.text },
  contactText: { ...typography.caption1, color: colors.textTertiary, marginTop: 2 },
  statsRow: { flexDirection: 'row', paddingTop: spacing.sm, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.separatorLight },
  statItem: { flex: 1, alignItems: 'center' },
  statValue: { ...typography.subhead, color: colors.text, fontWeight: '600' },
  statLabel: { ...typography.caption2, color: colors.textTertiary, marginTop: 2 },
  emptyContainer: { alignItems: 'center', paddingVertical: spacing.xxl },
  emptyText: { ...typography.body, color: colors.textTertiary, marginTop: spacing.md },
});

export default SupplierScreen;
