import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  TouchableOpacity,
  Alert,
  Dimensions,
} from 'react-native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import Animated, { FadeInDown, FadeInUp } from 'react-native-reanimated';
import { Button, Input } from '../../components';
import { useAuth } from '../../hooks/useAuth';
import { colors, typography, spacing, borderRadius, layout } from '../../theme';
import { AuthStackParamList } from '../../navigation/AuthStack';

type LoginScreenProps = {
  navigation: NativeStackNavigationProp<AuthStackParamList, 'Login'>;
};

const { width } = Dimensions.get('window');
const isTablet = width >= 768;

const LoginScreen: React.FC<LoginScreenProps> = ({ navigation }) => {
  const { login } = useAuth();
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState<{ identifier?: string; password?: string }>({});

  const validate = (): boolean => {
    const newErrors: { identifier?: string; password?: string } = {};
    if (!identifier.trim()) {
      newErrors.identifier = '请输入用户名或手机号';
    }
    if (!password) {
      newErrors.password = '请输入密码';
    } else if (password.length < 6) {
      newErrors.password = '密码至少6位';
    }
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleLogin = async () => {
    if (!validate()) return;

    setLoading(true);
    try {
      const user = await login(identifier.trim(), password);
      if (user.status === 'pending') {
        Alert.alert('账号审核中', '注册申请已提交，请等待管理员审批。');
      } else if (user.status === 'rejected') {
        Alert.alert('申请未通过', '当前账号申请未通过，请联系管理员后重新提交。');
      }
    } catch (error: any) {
      const message = error?.response?.data?.message || '登录失败，请检查用户名和密码';
      Alert.alert('登录失败', message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <ScrollView
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.content}>
          {/* Logo / Header */}
          <Animated.View entering={FadeInUp.duration(600).delay(100)} style={styles.header}>
            <View style={styles.logoContainer}>
              <Ionicons name="fish" size={48} color={colors.primary} />
            </View>
            <Text style={styles.title}>水产养殖管理</Text>
            <Text style={styles.subtitle}>鱼塘养殖管理系统</Text>
          </Animated.View>

          {/* Form */}
          <Animated.View entering={FadeInDown.duration(600).delay(300)} style={styles.form}>
            <Input
              label="用户名/手机号"
              placeholder="请输入用户名或手机号"
              leftIcon="person-outline"
              value={identifier}
              onChangeText={(text) => {
                setIdentifier(text);
                if (errors.identifier) setErrors((e) => ({ ...e, identifier: undefined }));
              }}
              error={errors.identifier}
              autoCapitalize="none"
              autoCorrect={false}
              returnKeyType="next"
            />

            <Input
              label="密码"
              placeholder="请输入密码"
              leftIcon="lock-closed-outline"
              value={password}
              onChangeText={(text) => {
                setPassword(text);
                if (errors.password) setErrors((e) => ({ ...e, password: undefined }));
              }}
              error={errors.password}
              isPassword
              returnKeyType="done"
              onSubmitEditing={handleLogin}
            />

            <Button
              title="登录"
              onPress={handleLogin}
              loading={loading}
              size="lg"
              style={styles.loginButton}
            />

            <View style={styles.footer}>
              <Text style={styles.footerText}>还没有账号？</Text>
              <TouchableOpacity onPress={() => navigation.navigate('Register')}>
                <Text style={styles.footerLink}>注册</Text>
              </TouchableOpacity>
            </View>
          </Animated.View>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  scrollContent: {
    flexGrow: 1,
    justifyContent: 'center',
  },
  content: {
    flex: 1,
    justifyContent: 'center',
    paddingHorizontal: layout.screenPadding,
    maxWidth: isTablet ? 480 : undefined,
    alignSelf: 'center',
    width: '100%',
  },
  header: {
    alignItems: 'center',
    marginBottom: spacing.xxxl,
  },
  logoContainer: {
    width: 88,
    height: 88,
    borderRadius: borderRadius.xxl,
    backgroundColor: colors.backgroundSecondary,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: spacing.lg,
  },
  title: {
    ...typography.largeTitle,
    color: colors.text,
    marginBottom: spacing.xs,
  },
  subtitle: {
    ...typography.subhead,
    color: colors.textTertiary,
  },
  form: {
    width: '100%',
  },
  loginButton: {
    marginTop: spacing.lg,
  },
  footer: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: spacing.xl,
  },
  footerText: {
    ...typography.subhead,
    color: colors.textTertiary,
  },
  footerLink: {
    ...typography.subhead,
    color: colors.primary,
    fontWeight: '600',
  },
});

export default LoginScreen;
