import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  TextInput,
  Alert,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import { colors, typography, spacing, borderRadius, shadows, layout } from '../../theme';
import { productionApi } from '../../api/production';

type DailyOpsCreateScreenProps = {
  navigation: NativeStackNavigationProp<any>;
};

const OP_TYPES = [
  { key: 'patrol', label: '巡塘', icon: 'eye-outline', color: '#007AFF' },
  { key: 'water_quality', label: '水质检测', icon: 'water-outline', color: '#5AC8FA' },
  { key: 'medication', label: '用药', icon: 'medical-outline', color: '#FF2D55' },
  { key: 'aeration', label: '增氧', icon: 'cloudy-outline', color: '#34C759' },
  { key: 'transfer', label: '转塘', icon: 'swap-horizontal-outline', color: '#AF52DE' },
  { key: 'harvest', label: '捕捞', icon: 'fish-outline', color: '#FF9500' },
  { key: 'other', label: '其他', icon: 'ellipsis-horizontal-outline', color: '#8E8E93' },
];

const DailyOpsCreateScreen: React.FC<DailyOpsCreateScreenProps> = ({ navigation }) => {
  const [opType, setOpType] = useState('patrol');
  const [pondName, setPondName] = useState('');
  const [description, setDescription] = useState('');
  const [observations, setObservations] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    if (!pondName.trim()) {
      Alert.alert('提示', '请填写塘口名称');
      return;
    }
    if (!description.trim() && !observations.trim()) {
      Alert.alert('提示', '请填写操作描述或观察记录');
      return;
    }
    try {
      setSubmitting(true);
      await productionApi.createDailyOps({
        operation_type: opType,
        pond_name: pondName.trim(),
        description: description.trim(),
        observations: observations.trim(),
        operation_date: new Date().toISOString().split('T')[0],
      });
      Alert.alert('成功', '操作记录已保存', [
        { text: '确定', onPress: () => navigation.goBack() },
      ]);
    } catch (err: any) {
      Alert.alert('保存失败', err?.message || '请稍后重试');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        {/* Header */}
        <View style={styles.header}>
          <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backBtn}>
            <Ionicons name="close" size={24} color={colors.text} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>新建日常操作</Text>
          <TouchableOpacity
            style={[styles.submitBtn, submitting && { opacity: 0.5 }]}
            onPress={handleSubmit}
            disabled={submitting}
          >
            {submitting ? (
              <ActivityIndicator size="small" color={colors.textInverse} />
            ) : (
              <Text style={styles.submitText}>保存</Text>
            )}
          </TouchableOpacity>
        </View>

        <ScrollView contentContainerStyle={styles.form} showsVerticalScrollIndicator={false}>
          {/* Operation Type */}
          <Text style={styles.sectionTitle}>操作类型</Text>
          <View style={styles.typeGrid}>
            {OP_TYPES.map((t) => (
              <TouchableOpacity
                key={t.key}
                style={[styles.typeChip, opType === t.key && { backgroundColor: t.color + '20', borderColor: t.color }]}
                onPress={() => setOpType(t.key)}
              >
                <Ionicons name={t.icon as any} size={20} color={opType === t.key ? t.color : colors.textTertiary} />
                <Text style={[styles.typeLabel, opType === t.key && { color: t.color, fontWeight: '600' }]}>
                  {t.label}
                </Text>
              </TouchableOpacity>
            ))}
          </View>

          {/* Pond Name */}
          <Text style={styles.sectionTitle}>塘口</Text>
          <TextInput
            style={styles.input}
            placeholder="输入塘口名称"
            placeholderTextColor={colors.gray3}
            value={pondName}
            onChangeText={setPondName}
          />

          {/* Description */}
          <Text style={styles.sectionTitle}>操作描述</Text>
          <TextInput
            style={[styles.input, styles.textArea]}
            placeholder="描述本次操作内容..."
            placeholderTextColor={colors.gray3}
            value={description}
            onChangeText={setDescription}
            multiline
            numberOfLines={4}
            textAlignVertical="top"
          />

          {/* Observations */}
          <Text style={styles.sectionTitle}>观察记录</Text>
          <TextInput
            style={[styles.input, styles.textArea]}
            placeholder="水面、鱼群状态、异常现象..."
            placeholderTextColor={colors.gray3}
            value={observations}
            onChangeText={setObservations}
            multiline
            numberOfLines={4}
            textAlignVertical="top"
          />
        </ScrollView>
      </KeyboardAvoidingView>
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
  submitBtn: {
    backgroundColor: colors.primary,
    paddingHorizontal: spacing.base,
    paddingVertical: spacing.sm,
    borderRadius: borderRadius.md,
    minWidth: 60,
    alignItems: 'center',
  },
  submitText: {
    ...typography.subhead,
    color: colors.textInverse,
    fontWeight: '600',
  },
  form: {
    padding: layout.screenPadding,
    paddingBottom: spacing.xxl,
  },
  sectionTitle: {
    ...typography.subhead,
    color: colors.text,
    fontWeight: '600',
    marginTop: spacing.lg,
    marginBottom: spacing.sm,
  },
  typeGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  typeChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: borderRadius.full,
    borderWidth: 1,
    borderColor: colors.separatorLight,
    backgroundColor: colors.backgroundSecondary,
  },
  typeLabel: {
    ...typography.caption1,
    color: colors.textSecondary,
  },
  input: {
    backgroundColor: colors.backgroundSecondary,
    borderRadius: borderRadius.md,
    padding: spacing.base,
    ...typography.body,
    color: colors.text,
    borderWidth: 1,
    borderColor: colors.separatorLight,
  },
  textArea: {
    minHeight: 100,
    paddingTop: spacing.md,
  },
});

export default DailyOpsCreateScreen;
