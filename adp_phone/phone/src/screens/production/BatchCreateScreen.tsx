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

type Props = {
  navigation: NativeStackNavigationProp<any>;
};

const BatchCreateScreen: React.FC<Props> = ({ navigation }) => {
  const [species, setSpecies] = useState('');
  const [pondName, setPondName] = useState('');
  const [source, setSource] = useState('');
  const [quantity, setQuantity] = useState('');
  const [weight, setWeight] = useState('');
  const [unitPrice, setUnitPrice] = useState('');
  const [stockingDate, setStockingDate] = useState(new Date().toISOString().split('T')[0]);
  const [expectedHarvestDate, setExpectedHarvestDate] = useState('');
  const [notes, setNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    if (!species.trim()) {
      Alert.alert('提示', '请填写养殖品种');
      return;
    }
    if (!pondName.trim()) {
      Alert.alert('提示', '请填写投放塘口');
      return;
    }
    if (!quantity.trim() || isNaN(Number(quantity))) {
      Alert.alert('提示', '请填写有效的投苗数量');
      return;
    }
    try {
      setSubmitting(true);
      await productionApi.createBatch({
        species: species.trim(),
        pond_name: pondName.trim(),
        source: source.trim() || undefined,
        stocking_quantity: Number(quantity),
        stocking_weight: weight ? Number(weight) : undefined,
        unit_price: unitPrice ? Number(unitPrice) : undefined,
        stocking_date: stockingDate,
        expected_harvest_date: expectedHarvestDate || undefined,
        notes: notes.trim() || undefined,
      });
      Alert.alert('成功', '养殖批次已创建', [
        { text: '确定', onPress: () => navigation.goBack() },
      ]);
    } catch (err: any) {
      Alert.alert('创建失败', err?.message || '请稍后重试');
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
        <View style={styles.header}>
          <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backBtn}>
            <Ionicons name="close" size={24} color={colors.text} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>新建养殖批次</Text>
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
          <Text style={styles.label}>养殖品种 *</Text>
          <TextInput
            style={styles.input}
            placeholder="如：鲈鱼、草鱼、南美白对虾"
            placeholderTextColor={colors.gray3}
            value={species}
            onChangeText={setSpecies}
          />

          <Text style={styles.label}>投放塘口 *</Text>
          <TextInput
            style={styles.input}
            placeholder="输入塘口名称"
            placeholderTextColor={colors.gray3}
            value={pondName}
            onChangeText={setPondName}
          />

          <Text style={styles.label}>苗种来源</Text>
          <TextInput
            style={styles.input}
            placeholder="供应商或来源"
            placeholderTextColor={colors.gray3}
            value={source}
            onChangeText={setSource}
          />

          <View style={styles.row}>
            <View style={styles.halfField}>
              <Text style={styles.label}>投苗数量(尾) *</Text>
              <TextInput
                style={styles.input}
                placeholder="0"
                placeholderTextColor={colors.gray3}
                value={quantity}
                onChangeText={setQuantity}
                keyboardType="number-pad"
              />
            </View>
            <View style={styles.halfField}>
              <Text style={styles.label}>投苗重量(kg)</Text>
              <TextInput
                style={styles.input}
                placeholder="0.0"
                placeholderTextColor={colors.gray3}
                value={weight}
                onChangeText={setWeight}
                keyboardType="decimal-pad"
              />
            </View>
          </View>

          <Text style={styles.label}>单价(元/尾)</Text>
          <TextInput
            style={styles.input}
            placeholder="0.00"
            placeholderTextColor={colors.gray3}
            value={unitPrice}
            onChangeText={setUnitPrice}
            keyboardType="decimal-pad"
          />

          <View style={styles.row}>
            <View style={styles.halfField}>
              <Text style={styles.label}>投苗日期</Text>
              <TextInput
                style={styles.input}
                placeholder="YYYY-MM-DD"
                placeholderTextColor={colors.gray3}
                value={stockingDate}
                onChangeText={setStockingDate}
              />
            </View>
            <View style={styles.halfField}>
              <Text style={styles.label}>预计出塘</Text>
              <TextInput
                style={styles.input}
                placeholder="YYYY-MM-DD"
                placeholderTextColor={colors.gray3}
                value={expectedHarvestDate}
                onChangeText={setExpectedHarvestDate}
              />
            </View>
          </View>

          <Text style={styles.label}>备注</Text>
          <TextInput
            style={[styles.input, styles.textArea]}
            placeholder="规格、密度要求等..."
            placeholderTextColor={colors.gray3}
            value={notes}
            onChangeText={setNotes}
            multiline
            numberOfLines={3}
            textAlignVertical="top"
          />
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: layout.screenPadding, paddingVertical: spacing.md, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.separatorLight },
  backBtn: { width: 36, height: 36, borderRadius: borderRadius.full, justifyContent: 'center', alignItems: 'center' },
  headerTitle: { ...typography.headline, color: colors.text, flex: 1, textAlign: 'center' },
  submitBtn: { backgroundColor: colors.primary, paddingHorizontal: spacing.base, paddingVertical: spacing.sm, borderRadius: borderRadius.md, minWidth: 60, alignItems: 'center' },
  submitText: { ...typography.subhead, color: colors.textInverse, fontWeight: '600' },
  form: { padding: layout.screenPadding, paddingBottom: spacing.xxl },
  label: { ...typography.subhead, color: colors.text, fontWeight: '600', marginTop: spacing.lg, marginBottom: spacing.sm },
  input: { backgroundColor: colors.backgroundSecondary, borderRadius: borderRadius.md, padding: spacing.base, ...typography.body, color: colors.text, borderWidth: 1, borderColor: colors.separatorLight },
  textArea: { minHeight: 80, paddingTop: spacing.md },
  row: { flexDirection: 'row', gap: spacing.md },
  halfField: { flex: 1 },
});

export default BatchCreateScreen;
