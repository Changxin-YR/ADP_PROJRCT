import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Platform,
  Alert,
  Dimensions,
} from 'react-native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Button, Input } from '../../components';
import { pondsApi } from '../../api/ponds';
import { colors, typography, spacing, borderRadius, layout } from '../../theme';
import { PondsStackParamList } from '../../navigation/PondsStack';

type PondCreateScreenProps = {
  navigation: NativeStackNavigationProp<PondsStackParamList, 'PondCreate'>;
};

const { width } = Dimensions.get('window');
const isTablet = width >= 768;

const PondCreateScreen: React.FC<PondCreateScreenProps> = ({ navigation }) => {
  const [name, setName] = useState('');
  const [code, setCode] = useState('');
  const [area, setArea] = useState('');
  const [depth, setDepth] = useState('');
  const [waterSource, setWaterSource] = useState('');
  const [loading, setLoading] = useState(false);

  const handleCreate = async () => {
    if (!name || !code || !area || !depth) {
      Alert.alert('提示', '请填写所有必填项');
      return;
    }
    setLoading(true);
    try {
      await pondsApi.create({
        name,
        code,
        area: parseFloat(area),
        depth: parseFloat(depth),
        water_source: waterSource || undefined,
      });
      Alert.alert('成功', '塘口创建成功', [
        { text: '确定', onPress: () => navigation.goBack() },
      ]);
    } catch (err: any) {
      const msg = err?.response?.data?.message || '创建失败，请稍后重试';
      Alert.alert('错误', msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton}>
          <Ionicons name="close" size={24} color={colors.text} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>新建塘口</Text>
        <View style={{ width: 36 }} />
      </View>

      <ScrollView
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.form}>
          <Input label="塘口名称 *" placeholder="如：A1号塘" value={name} onChangeText={setName} leftIcon="water-outline" />
          <Input label="编号 *" placeholder="如：A1" value={code} onChangeText={setCode} leftIcon="barcode-outline" />
          <Input label="面积（m²）*" placeholder="如：2000" value={area} onChangeText={setArea} keyboardType="numeric" leftIcon="resize-outline" />
          <Input label="深度（m）*" placeholder="如：2.5" value={depth} onChangeText={setDepth} keyboardType="decimal-pad" leftIcon="arrow-down-outline" />
          <Input label="水源" placeholder="如：河流、井水" value={waterSource} onChangeText={setWaterSource} leftIcon="water-outline" />

          <Button title="创建塘口" onPress={handleCreate} loading={loading} size="lg" style={styles.createButton} />
        </View>
      </ScrollView>
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
  scrollContent: {
    padding: layout.screenPadding,
  },
  form: {
    maxWidth: isTablet ? 480 : undefined,
    alignSelf: isTablet ? 'center' : undefined,
    width: '100%',
  },
  createButton: {
    marginTop: spacing.xl,
  },
});

export default PondCreateScreen;
