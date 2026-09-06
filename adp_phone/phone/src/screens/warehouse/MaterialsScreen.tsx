import React, { useState, useCallback, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  RefreshControl,
  ActivityIndicator,
  Dimensions,
} from 'react-native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import { masterDataApi } from '../../api/masterData';
import { Material } from '../../types';
import { colors, typography, spacing, borderRadius, shadows, layout } from '../../theme';
import { WarehouseStackParamList } from '../../navigation/WarehouseStack';

type MaterialsScreenProps = {
  navigation: NativeStackNavigationProp<WarehouseStackParamList, 'Materials'>;
};

const { width } = Dimensions.get('window');
const isTablet = width >= 768;

const getCategoryIcon = (cat: string): keyof typeof Ionicons.glyphMap => {
  switch (cat) {
    case 'feed': return 'nutrition';
    case 'medicine': return 'medical';
    case 'equipment': return 'construct';
    case 'chemical': return 'flask';
    default: return 'cube';
  }
};

const getCategoryColor = (cat: string): string => {
  switch (cat) {
    case 'feed': return colors.warning;
    case 'medicine': return colors.error;
    case 'equipment': return colors.primary;
    case 'chemical': return colors.info;
    default: return colors.gray1;
  }
};

const getCategoryLabel = (cat: string): string => {
  switch (cat) {
    case 'feed': return '饲料';
    case 'medicine': return '动保';
    case 'equipment': return '设备';
    case 'chemical': return '化学品';
    default: return '其他';
  }
};

const MaterialsScreen: React.FC<MaterialsScreenProps> = ({ navigation }) => {
  const [materials, setMaterials] = useState<Material[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);

  const fetchMaterials = useCallback(async (pageNum = 1, refresh = false) => {
    try {
      if (refresh) setRefreshing(true);
      else if (pageNum === 1) setLoading(true);
      const data = await masterDataApi.listMaterials(pageNum, 20);
      if (refresh || pageNum === 1) {
        setMaterials(data.items);
      } else {
        setMaterials((prev) => [...prev, ...data.items]);
      }
      setHasMore(pageNum < data.pages);
      setPage(pageNum);
    } catch (err) {
      console.warn('Failed to load materials', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchMaterials(1);
  }, [fetchMaterials]);

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>仓储管理</Text>
        <View style={styles.headerActions}>
          <TouchableOpacity
            style={styles.headerButton}
            onPress={() => navigation.navigate('StockAlerts')}
          >
            <Ionicons name="alert-circle-outline" size={22} color={colors.error} />
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.headerButton}
            onPress={() => navigation.navigate('StockInOut', {})}
          >
            <Ionicons name="swap-horizontal" size={22} color={colors.primary} />
          </TouchableOpacity>
        </View>
      </View>

      {loading && materials.length === 0 ? (
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={colors.primary} />
        </View>
      ) : (
        <FlatList
          data={materials}
          keyExtractor={(item) => String(item.id)}
          contentContainerStyle={styles.listContent}
          showsVerticalScrollIndicator={false}
          onEndReached={() => {
            if (hasMore && !loading) fetchMaterials(page + 1);
          }}
          onEndReachedThreshold={0.3}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={() => fetchMaterials(1, true)} tintColor={colors.primary} />
          }
          renderItem={({ item }) => {
            return (
              <TouchableOpacity
                style={styles.materialCard}
                onPress={() => navigation.navigate('StockInOut', { materialId: String(item.id) })}
                activeOpacity={0.7}
              >
                <View style={[styles.materialIcon, { backgroundColor: getCategoryColor(item.category) + '15' }]}>
                  <Ionicons name={getCategoryIcon(item.category)} size={22} color={getCategoryColor(item.category)} />
                </View>
                <View style={styles.materialInfo}>
                  <Text style={styles.materialName}>{item.name}</Text>
                  <Text style={styles.materialCategory}>{getCategoryLabel(item.category)}</Text>
                </View>
                <View style={styles.stockInfo}>
                  <Text style={styles.stockUnit}>{item.unit}</Text>
                </View>
              </TouchableOpacity>
            );
          }}
          ListEmptyComponent={
            <View style={styles.emptyContainer}>
              <Ionicons name="cube-outline" size={48} color={colors.gray3} />
              <Text style={styles.emptyText}>暂无物料数据</Text>
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
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: layout.screenPadding,
    paddingVertical: spacing.base,
  },
  title: {
    ...typography.largeTitle,
    color: colors.text,
  },
  headerActions: {
    flexDirection: 'row',
  },
  headerButton: {
    width: 36,
    height: 36,
    borderRadius: borderRadius.full,
    backgroundColor: colors.background,
    justifyContent: 'center',
    alignItems: 'center',
    marginLeft: spacing.sm,
    ...shadows.sm,
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
  materialCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.background,
    borderRadius: borderRadius.lg,
    padding: spacing.base,
    marginBottom: spacing.sm,
    ...shadows.sm,
  },
  materialIcon: {
    width: 44,
    height: 44,
    borderRadius: borderRadius.md,
    justifyContent: 'center',
    alignItems: 'center',
  },
  materialInfo: {
    flex: 1,
    marginLeft: spacing.md,
  },
  materialName: {
    ...typography.body,
    color: colors.text,
    fontWeight: '500',
  },
  materialCategory: {
    ...typography.caption1,
    color: colors.textTertiary,
    marginTop: 2,
  },
  stockInfo: {
    alignItems: 'flex-end',
  },
  stockValue: {
    ...typography.headline,
    color: colors.text,
  },
  stockLow: {
    color: colors.error,
  },
  stockUnit: {
    ...typography.caption1,
    color: colors.textTertiary,
  },
  lowBadge: {
    marginTop: spacing.xs,
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
    backgroundColor: colors.error + '15',
    borderRadius: borderRadius.full,
  },
  lowBadgeText: {
    ...typography.caption2,
    color: colors.error,
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

export default MaterialsScreen;
