import React, { useState, useCallback, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  Dimensions,
  RefreshControl,
  ActivityIndicator,
} from 'react-native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import { colors, typography, spacing, borderRadius, shadows, layout } from '../../theme';
import { PondsStackParamList } from '../../navigation/PondsStack';
import { Pond, POND_STATUS_LABELS, POND_STATUS_COLORS } from '../../types';
import { pondsApi } from '../../api/ponds';

type PondListScreenProps = {
  navigation: NativeStackNavigationProp<PondsStackParamList, 'PondList'>;
};

const { width } = Dimensions.get('window');
const isTablet = width >= 768;

const PondListScreen: React.FC<PondListScreenProps> = ({ navigation }) => {
  const [ponds, setPonds] = useState<Pond[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const numColumns = isTablet ? 2 : 1;

  const fetchPonds = useCallback(async (refresh = false) => {
    try {
      if (refresh) setRefreshing(true);
      const data = await pondsApi.list(1, 50);
      setPonds(data.items);
    } catch (err) {
      console.warn('Failed to load ponds', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchPonds();
  }, [fetchPonds]);

  const renderPondCard = ({ item }: { item: Pond }) => (
    <TouchableOpacity
      style={[styles.cardWrapper, isTablet && styles.cardWrapperTablet]}
      onPress={() => navigation.navigate('PondDetail', { pondId: String(item.id) })}
      activeOpacity={0.7}
    >
      <View style={styles.pondCard}>
        <View style={styles.cardHeader}>
          <View style={styles.pondIcon}>
            <Ionicons name="water" size={20} color={colors.primary} />
          </View>
          <View style={[styles.statusBadge, { backgroundColor: (POND_STATUS_COLORS[item.pond_status] || '#8E8E93') + '20' }]}>
            <View style={[styles.statusDot, { backgroundColor: POND_STATUS_COLORS[item.pond_status] || '#8E8E93' }]} />
            <Text style={[styles.statusText, { color: POND_STATUS_COLORS[item.pond_status] || '#8E8E93' }]}>
              {POND_STATUS_LABELS[item.pond_status] || item.pond_status}
            </Text>
          </View>
        </View>
        <Text style={styles.pondName}>{item.name}</Text>
        <Text style={styles.pondSpecies}>{item.species || '暂无养殖品种'}</Text>
        <View style={styles.pondStats}>
          <View style={styles.pondStat}>
            <Text style={styles.statValue}>{item.capacity_mu}</Text>
            <Text style={styles.statUnit}>亩</Text>
          </View>
          <View style={styles.divider} />
          <View style={styles.pondStat}>
            <Text style={styles.statValue}>{item.manager_name}</Text>
          </View>
        </View>
      </View>
    </TouchableOpacity>
  );

  if (loading && ponds.length === 0) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.header}>
          <Text style={styles.title}>塘口</Text>
        </View>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={colors.primary} />
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>塘口</Text>
        <TouchableOpacity
          style={styles.addButton}
          onPress={() => navigation.navigate('PondCreate')}
        >
          <Ionicons name="add" size={24} color={colors.textInverse} />
        </TouchableOpacity>
      </View>
      <FlatList
        data={ponds}
        keyExtractor={(item) => String(item.id)}
        renderItem={renderPondCard}
        numColumns={numColumns}
        key={numColumns}
        contentContainerStyle={styles.listContent}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={() => fetchPonds(true)} tintColor={colors.primary} />
        }
        ListEmptyComponent={
          <View style={styles.emptyContainer}>
            <Ionicons name="water-outline" size={48} color={colors.gray3} />
            <Text style={styles.emptyText}>暂无塘口数据</Text>
          </View>
        }
      />
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
  addButton: {
    width: 40,
    height: 40,
    borderRadius: borderRadius.full,
    backgroundColor: colors.primary,
    justifyContent: 'center',
    alignItems: 'center',
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
  cardWrapper: {
    marginBottom: spacing.md,
  },
  cardWrapperTablet: {
    flex: 0.5,
    paddingHorizontal: spacing.xs,
  },
  pondCard: {
    backgroundColor: colors.background,
    borderRadius: borderRadius.lg,
    padding: spacing.base,
    ...shadows.md,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.md,
  },
  pondIcon: {
    width: 36,
    height: 36,
    borderRadius: borderRadius.md,
    backgroundColor: colors.primary + '15',
    justifyContent: 'center',
    alignItems: 'center',
  },
  statusBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
    borderRadius: borderRadius.full,
  },
  statusDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    marginRight: spacing.xs,
  },
  statusText: {
    ...typography.caption2,
    fontWeight: '600',
  },
  pondName: {
    ...typography.headline,
    color: colors.text,
    marginBottom: spacing.xs,
  },
  pondSpecies: {
    ...typography.subhead,
    color: colors.textTertiary,
    marginBottom: spacing.md,
  },
  pondStats: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingTop: spacing.md,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.separatorLight,
  },
  pondStat: {
    flexDirection: 'row',
    alignItems: 'baseline',
  },
  statValue: {
    ...typography.headline,
    color: colors.text,
  },
  statUnit: {
    ...typography.caption1,
    color: colors.textTertiary,
    marginLeft: 3,
  },
  divider: {
    width: 1,
    height: 16,
    backgroundColor: colors.separatorLight,
    marginHorizontal: spacing.base,
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

export default PondListScreen;
