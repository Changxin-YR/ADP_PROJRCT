import React, { useState, useCallback, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  RefreshControl,
  Dimensions,
} from 'react-native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RouteProp } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Card } from '../../components';
import { colors, typography, spacing, borderRadius, shadows, layout } from '../../theme';
import { PondsStackParamList } from '../../navigation/PondsStack';
import { pondsApi } from '../../api/ponds';
import { Pond, POND_STATUS_LABELS, POND_STATUS_COLORS } from '../../types';

type PondDetailScreenProps = {
  navigation: NativeStackNavigationProp<PondsStackParamList, 'PondDetail'>;
  route: RouteProp<PondsStackParamList, 'PondDetail'>;
};

const { width } = Dimensions.get('window');
const isTablet = width >= 768;

const PondDetailScreen: React.FC<PondDetailScreenProps> = ({ navigation, route }) => {
  const { pondId } = route.params;
  const [pond, setPond] = useState<Pond | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchPond = useCallback(async (refresh = false) => {
    try {
      if (refresh) setRefreshing(true);
      const data = await pondsApi.getById(Number(pondId));
      setPond(data);
    } catch (err) {
      console.warn('Failed to load pond detail', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [pondId]);

  useEffect(() => {
    fetchPond();
  }, [fetchPond]);

  if (loading) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.header}>
          <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton}>
            <Ionicons name="arrow-back" size={24} color={colors.text} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>塘口详情</Text>
          <View style={{ width: 36 }} />
        </View>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={colors.primary} />
        </View>
      </SafeAreaView>
    );
  }

  const statusColor = (pond?.pond_status && POND_STATUS_COLORS[pond.pond_status]) || '#8E8E93';
  const statusLabel = (pond?.pond_status && POND_STATUS_LABELS[pond.pond_status]) || pond?.pond_status || '未知';

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={() => fetchPond(true)} tintColor={colors.primary} />
        }
      >
        {/* Header */}
        <View style={styles.header}>
          <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton}>
            <Ionicons name="arrow-back" size={24} color={colors.text} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>塘口详情</Text>
          <TouchableOpacity style={styles.editButton}>
            <Ionicons name="create-outline" size={22} color={colors.primary} />
          </TouchableOpacity>
        </View>

        <View style={styles.content}>
          {/* Pond Info */}
          <Card style={styles.section}>
            <View style={styles.pondHeader}>
              <View style={styles.pondIconLarge}>
                <Ionicons name="water" size={32} color={colors.primary} />
              </View>
              <View style={styles.pondHeaderInfo}>
                <Text style={styles.pondName}>{pond?.name || `塘口 #${pondId}`}</Text>
                <View style={styles.statusRow}>
                  <View style={[styles.activeDot, { backgroundColor: statusColor }]} />
                  <Text style={[styles.statusLabel, { color: statusColor }]}>{statusLabel}</Text>
                </View>
              </View>
            </View>
          </Card>

          {/* Parameters */}
          <Card title="基本信息" style={styles.section}>
            <View style={styles.paramGrid}>
              {[
                { label: '面积', value: `${pond?.capacity_mu || '--'} 亩`, icon: 'resize-outline' },
                { label: '深度', value: `${pond?.depth || '--'} m`, icon: 'arrow-down-outline' },
                { label: '水源', value: pond?.water_source || '--', icon: 'water-outline' },
                { label: '养殖品种', value: pond?.species || '--', icon: 'fish-outline' },
                { label: '管理员', value: pond?.manager_name || '--', icon: 'person-outline' },
                { label: '所属分组', value: pond?.group_name || '--', icon: 'albums-outline' },
              ].map((param, index) => (
                <View key={index} style={styles.paramItem}>
                  <Ionicons name={param.icon as any} size={18} color={colors.textTertiary} />
                  <Text style={styles.paramLabel}>{param.label}</Text>
                  <Text style={styles.paramValue}>{param.value}</Text>
                </View>
              ))}
            </View>
          </Card>

          {/* Water Quality */}
          <Card title="水质指标" subtitle="最近一次检测" style={styles.section}>
            <View style={styles.qualityGrid}>
              {[
                { label: '水温', value: pond?.water_temp ? `${pond.water_temp}°C` : '--', status: 'normal' },
                { label: 'pH', value: pond?.ph || '--', status: 'normal' },
                { label: '溶氧', value: pond?.dissolved_oxygen ? `${pond.dissolved_oxygen} mg/L` : '--', status: 'normal' },
                { label: '氨氮', value: pond?.ammonia ? `${pond.ammonia} mg/L` : '--', status: 'normal' },
              ].map((item, index) => (
                <View key={index} style={styles.qualityItem}>
                  <Text style={styles.qualityValue}>{item.value}</Text>
                  <Text style={styles.qualityLabel}>{item.label}</Text>
                </View>
              ))}
            </View>
          </Card>

          {/* Quick Actions */}
          <Card title="快捷操作" style={styles.section}>
            <View style={styles.actionsRow}>
              {[
                { icon: 'nutrition-outline' as const, label: '投喂', color: '#FF9500', onPress: () => navigation.getParent()?.navigate('FeedingTab') },
                { icon: 'eye-outline' as const, label: '巡塘', color: '#007AFF', onPress: () => {} },
                { icon: 'fish-outline' as const, label: '批次', color: '#34C759', onPress: () => navigation.navigate('Batches') },
                { icon: 'analytics-outline' as const, label: '抽样', color: '#5AC8FA', onPress: () => navigation.navigate('Sampling') },
              ].map((action, index) => (
                <TouchableOpacity key={index} style={styles.actionItem} activeOpacity={0.7} onPress={action.onPress}>
                  <View style={[styles.actionIcon, { backgroundColor: action.color + '15' }]}>
                    <Ionicons name={action.icon} size={22} color={action.color} />
                  </View>
                  <Text style={styles.actionLabel}>{action.label}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </Card>
        </View>
      </ScrollView>
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
  editButton: {
    width: 36,
    height: 36,
    borderRadius: borderRadius.full,
    justifyContent: 'center',
    alignItems: 'center',
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  content: {
    padding: layout.screenPadding,
    maxWidth: isTablet ? layout.maxContentWidth : undefined,
    alignSelf: isTablet ? 'center' : undefined,
    width: '100%',
  },
  section: {
    marginBottom: spacing.base,
  },
  pondHeader: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  pondIconLarge: {
    width: 56,
    height: 56,
    borderRadius: borderRadius.lg,
    backgroundColor: colors.primary + '15',
    justifyContent: 'center',
    alignItems: 'center',
  },
  pondHeaderInfo: {
    marginLeft: spacing.base,
  },
  pondName: {
    ...typography.title2,
    color: colors.text,
  },
  statusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: spacing.xs,
  },
  activeDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginRight: spacing.xs,
  },
  statusLabel: {
    ...typography.subhead,
    fontWeight: '500',
  },
  paramGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginTop: spacing.md,
  },
  paramItem: {
    width: '50%',
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: spacing.md,
    gap: spacing.sm,
  },
  paramLabel: {
    ...typography.caption1,
    color: colors.textTertiary,
  },
  paramValue: {
    ...typography.body,
    color: colors.text,
    fontWeight: '500',
  },
  qualityGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginTop: spacing.md,
  },
  qualityItem: {
    width: '50%',
    alignItems: 'center',
    paddingVertical: spacing.md,
  },
  qualityValue: {
    ...typography.title3,
    color: colors.text,
  },
  qualityLabel: {
    ...typography.caption1,
    color: colors.textTertiary,
    marginTop: 4,
  },
  actionsRow: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    paddingVertical: spacing.md,
  },
  actionItem: {
    alignItems: 'center',
    gap: spacing.sm,
  },
  actionIcon: {
    width: 44,
    height: 44,
    borderRadius: borderRadius.md,
    justifyContent: 'center',
    alignItems: 'center',
  },
  actionLabel: {
    ...typography.caption1,
    color: colors.text,
    fontWeight: '500',
  },
});

export default PondDetailScreen;
