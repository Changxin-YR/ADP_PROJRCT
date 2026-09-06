import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Alert,
  ActivityIndicator,
  RefreshControl,
  Modal,
} from 'react-native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import * as DocumentPicker from 'expo-document-picker';
import { File, Paths } from 'expo-file-system';
import * as Sharing from 'expo-sharing';
import { SafeAreaView } from 'react-native-safe-area-context';
import { dataExchangeApi, MobileUploadFile } from '../../api/dataExchange';
import { DataTemplate } from '../../types';
import { useAuth } from '../../hooks/useAuth';
import { colors, typography, spacing, borderRadius, shadows, layout } from '../../theme';

type DataExchangeScreenProps = {
  navigation: NativeStackNavigationProp<any>;
};

const MODULE_COLORS: Record<string, string> = {
  ponds: '#007AFF',
  production: '#FF9500',
  warehouse: '#AF52DE',
  cost: '#34C759',
  sales: '#5AC8FA',
  purchase: '#FF3B30',
  master_data: '#007AFF',
};

const MODULE_ICONS: Record<string, keyof typeof Ionicons.glyphMap> = {
  ponds: 'water-outline',
  production: 'fish-outline',
  warehouse: 'cube-outline',
  cost: 'calculator-outline',
  sales: 'cash-outline',
  purchase: 'cart-outline',
  master_data: 'server-outline',
};

const DataExchangeScreen: React.FC<DataExchangeScreenProps> = ({ navigation }) => {
  const { user } = useAuth();
  const [templates, setTemplates] = useState<DataTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [templatePickerMode, setTemplatePickerMode] = useState<'import' | 'export' | null>(null);
  const [pickedFile, setPickedFile] = useState<MobileUploadFile | null>(null);

  const fetchTemplates = useCallback(async (refresh = false) => {
    try {
      if (refresh) setRefreshing(true);
      const data = await dataExchangeApi.listTemplates();
      setTemplates(Array.isArray(data) ? data : (data as any).items || []);
    } catch (err) {
      console.warn('Failed to load templates', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchTemplates();
  }, [fetchTemplates]);

  const saveAndShareExport = async (template: DataTemplate) => {
    if (!user?.organization_id) throw new Error('组织范围不可用');
    const payload = await dataExchangeApi.exportData({
      organization_id: user.organization_id,
      resource: template.code,
      format: 'xlsx',
      filters: {},
    });
    if (!payload || typeof payload.arrayBuffer !== 'function') throw new Error('导出文件为空');
    const file = new File(Paths.cache, `adp-${template.code}-${Date.now()}.xlsx`);
    file.write(new Uint8Array(await payload.arrayBuffer()));
    if (!(await Sharing.isAvailableAsync())) throw new Error('当前设备不支持分享文件');
    await Sharing.shareAsync(file.uri, {
      mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      dialogTitle: '分享导出文件',
    });
  };

  const handleExport = (template: DataTemplate) => {
    Alert.alert(
      '导出确认',
      `确定导出 ${template.name} 数据？`,
      [
        { text: '取消', style: 'cancel' },
        {
          text: '导出',
          onPress: async () => {
            setBusy(true);
            try {
              await saveAndShareExport(template);
            } catch {
              Alert.alert('错误', '导出失败，请稍后重试。');
            } finally {
              setBusy(false);
            }
          },
        },
      ]
    );
  };

  const chooseTemplate = (template: DataTemplate) => {
    const file = pickedFile;
    setTemplatePickerMode(null);
    setPickedFile(null);
    if (templatePickerMode === 'export') {
      handleExport(template);
    } else if (file) {
      previewImport(template, file);
    }
  };

  const previewImport = async (template: DataTemplate, file: MobileUploadFile) => {
    if (!user?.organization_id) {
      Alert.alert('错误', '组织范围不可用');
      return;
    }
    setBusy(true);
    try {
      const result = await dataExchangeApi.previewImport(user.organization_id, template.code, file);
      const batch = result?.batch;
      if (!batch) throw new Error('导入预览结果无效');
      if (batch.status !== 'ready' || batch.errors?.length) {
        const firstErrors = (batch.errors || []).slice(0, 3).map((item: any) => `${item.row || '-'}行：${item.message || '数据无效'}`).join('\n');
        Alert.alert('校验未通过', firstErrors || '文件存在错误，无法确认导入。');
        return;
      }
      Alert.alert('预览通过', `共 ${batch.preview_rows?.length || 0} 行数据，确认后将写入草稿台账。`, [
        { text: '取消', style: 'cancel' },
        {
          text: '确认导入',
          onPress: async () => {
            setBusy(true);
            try {
              await dataExchangeApi.confirmImport(Number(batch.id));
              Alert.alert('成功', '数据已导入草稿台账。');
            } catch {
              Alert.alert('错误', '确认导入失败，请稍后重试。');
            } finally {
              setBusy(false);
            }
          },
        },
      ]);
    } catch {
      Alert.alert('错误', '导入预览失败，请检查文件和模板后重试。');
    } finally {
      setBusy(false);
    }
  };

  const handleImport = async () => {
    try {
      const result = await DocumentPicker.getDocumentAsync({
        type: [
          'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
          'application/vnd.ms-excel',
        ],
        copyToCacheDirectory: true,
      });
      if (result.canceled || !result.assets?.[0]) return;
      const asset = result.assets[0];
      setPickedFile({ uri: asset.uri, name: asset.name, type: asset.mimeType || 'application/octet-stream' });
      setTemplatePickerMode('import');
    } catch {
      Alert.alert('错误', '无法打开文件选择器，请稍后重试。');
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={24} color={colors.text} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>数据导入导出</Text>
        <View style={{ width: 36 }} />
      </View>

      <ScrollView
        showsVerticalScrollIndicator={false}
        contentContainerStyle={styles.scrollContent}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={() => fetchTemplates(true)} tintColor={colors.primary} />
        }
      >
        {/* Quick Actions */}
        <View style={styles.actionsRow}>
          <TouchableOpacity style={styles.actionCard} onPress={handleImport} activeOpacity={0.7}>
            <View style={[styles.actionIcon, { backgroundColor: '#007AFF15' }]}>
              <Ionicons name="cloud-upload-outline" size={28} color="#007AFF" />
            </View>
            <Text style={styles.actionLabel}>数据导入</Text>
            <Text style={styles.actionDesc}>上传数据文件</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.actionCard}
            onPress={() => {
              if (!templates.length) {
                Alert.alert('提示', '暂无可用模板');
                return;
              }
              setTemplatePickerMode('export');
            }}
            activeOpacity={0.7}
          >
            <View style={[styles.actionIcon, { backgroundColor: '#34C75915' }]}>
              <Ionicons name="cloud-download-outline" size={28} color="#34C759" />
            </View>
            <Text style={styles.actionLabel}>数据导出</Text>
            <Text style={styles.actionDesc}>下载业务数据</Text>
          </TouchableOpacity>
        </View>

        {/* Export Templates */}
        <Text style={styles.sectionTitle}>导出模板</Text>
        {loading ? (
          <ActivityIndicator size="large" color={colors.primary} style={{ marginTop: 40 }} />
        ) : templates.length === 0 ? (
          <View style={styles.emptyContainer}>
            <Ionicons name="document-outline" size={48} color={colors.gray3} />
            <Text style={styles.emptyText}>暂无可用模板</Text>
          </View>
        ) : (
          templates.map((template) => {
            const entityColor = MODULE_COLORS[template.entity_type || template.code] || '#8E8E93';
            const entityIcon = MODULE_ICONS[template.entity_type || template.code] || 'document-outline';
            return (
              <TouchableOpacity
                key={template.id}
                style={styles.templateItem}
                onPress={() => handleExport(template)}
                activeOpacity={0.6}
              >
                <View style={[styles.templateIcon, { backgroundColor: entityColor + '15' }]}>
                  <Ionicons name={entityIcon} size={20} color={entityColor} />
                </View>
                <View style={styles.templateContent}>
                  <Text style={styles.templateName}>{template.name}</Text>
                  <Text style={styles.templateModule}>{template.group || template.entity_type || template.code}</Text>
                </View>
                <Ionicons name="download-outline" size={20} color={colors.primary} />
              </TouchableOpacity>
            );
          })
        )}
      </ScrollView>
      <Modal visible={templatePickerMode !== null} transparent animationType="slide" onRequestClose={() => {
        setTemplatePickerMode(null);
        setPickedFile(null);
      }}>
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>{templatePickerMode === 'import' ? '选择导入模板' : '选择导出数据'}</Text>
              <TouchableOpacity onPress={() => {
                setTemplatePickerMode(null);
                setPickedFile(null);
              }}>
                <Ionicons name="close" size={24} color={colors.textSecondary} />
              </TouchableOpacity>
            </View>
            <ScrollView>
              {templates.filter((template) => templatePickerMode !== 'import' || template.importable !== false).map((template) => (
                <TouchableOpacity key={template.id} style={styles.modalItem} onPress={() => chooseTemplate(template)}>
                  <Text style={styles.templateName}>{template.name}</Text>
                  <Text style={styles.templateModule}>{template.code}</Text>
                </TouchableOpacity>
              ))}
            </ScrollView>
          </View>
        </View>
      </Modal>
      {busy && (
        <View style={styles.busyOverlay}>
          <ActivityIndicator size="large" color={colors.primary} />
        </View>
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
    textAlign: 'center',
  },
  scrollContent: {
    padding: layout.screenPadding,
    paddingTop: 0,
  },
  actionsRow: {
    flexDirection: 'row',
    marginBottom: spacing.xl,
    gap: spacing.md,
  },
  actionCard: {
    flex: 1,
    backgroundColor: colors.background,
    borderRadius: borderRadius.lg,
    padding: spacing.base,
    alignItems: 'center',
    ...shadows.md,
  },
  actionIcon: {
    width: 56,
    height: 56,
    borderRadius: borderRadius.lg,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: spacing.sm,
  },
  actionLabel: {
    ...typography.headline,
    color: colors.text,
  },
  actionDesc: {
    ...typography.caption1,
    color: colors.textTertiary,
    marginTop: 2,
  },
  sectionTitle: {
    ...typography.headline,
    color: colors.text,
    marginBottom: spacing.md,
  },
  templateItem: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.background,
    borderRadius: borderRadius.lg,
    padding: spacing.base,
    marginBottom: spacing.sm,
    ...shadows.sm,
  },
  templateIcon: {
    width: 40,
    height: 40,
    borderRadius: borderRadius.md,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: spacing.md,
  },
  templateContent: {
    flex: 1,
  },
  templateName: {
    ...typography.body,
    color: colors.text,
  },
  templateModule: {
    ...typography.caption1,
    color: colors.textTertiary,
    marginTop: 2,
  },
  emptyContainer: {
    alignItems: 'center',
    paddingTop: 60,
  },
  emptyText: {
    ...typography.body,
    color: colors.textTertiary,
    marginTop: spacing.md,
  },
  modalOverlay: {
    flex: 1,
    justifyContent: 'flex-end',
    backgroundColor: '#00000055',
  },
  modalContent: {
    maxHeight: '80%',
    backgroundColor: colors.background,
    borderTopLeftRadius: borderRadius.lg,
    borderTopRightRadius: borderRadius.lg,
    padding: spacing.base,
  },
  modalHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.sm,
  },
  modalTitle: {
    ...typography.headline,
    color: colors.text,
  },
  modalItem: {
    paddingVertical: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.separatorLight,
  },
  busyOverlay: {
    ...StyleSheet.absoluteFill,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#FFFFFF99',
  },
});

export default DataExchangeScreen;
