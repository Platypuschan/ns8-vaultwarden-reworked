import java.io.DataInputStream;
import java.io.InputStream;
import java.lang.invoke.MethodType;
import java.lang.reflect.Modifier;
import java.nio.file.Path;
import java.util.HashSet;
import java.util.Set;
import java.util.jar.JarFile;
import java.util.regex.Pattern;

/** Resolve the overlay's actual REST bytecode references using only runtime JARs.
 * The compile-time API can be newer, but every referenced class/member must exist.
 * This is a linkage guard, not a claim that REST 4 implementations run on REST 3.
 */
public final class RestLinkageCheck {
    private static final String PREFIX = "jakarta/ws/rs/";
    private static final Set<String> checked = new HashSet<>();
    private static final Pattern TYPE = Pattern.compile("L(jakarta/ws/rs/[^;<>]+);");

    private static Class<?> load(String name) throws ClassNotFoundException {
        return Class.forName(name.replace('/', '.'), false, RestLinkageCheck.class.getClassLoader());
    }

    private static void checkClass(String name) throws ReflectiveOperationException {
        if (name.startsWith(PREFIX)) {
            load(name);
            checked.add(name);
        }
    }

    private static void check(InputStream stream) throws Exception {
        var in = new DataInputStream(stream);
        if (in.readInt() != 0xcafebabe) throw new IllegalArgumentException("not a class");
        in.readUnsignedShort();
        in.readUnsignedShort();
        int count = in.readUnsignedShort();
        var values = new Object[count];
        var tags = new int[count];
        for (int i = 1; i < count; i++) {
            tags[i] = in.readUnsignedByte();
            switch (tags[i]) {
                case 1 -> values[i] = in.readUTF();
                case 3, 4 -> in.readInt();
                case 5, 6 -> { in.readLong(); i++; }
                case 7, 8, 16, 19, 20 -> values[i] = in.readUnsignedShort();
                case 9, 10, 11, 12, 17, 18 -> values[i] = new int[] {in.readUnsignedShort(), in.readUnsignedShort()};
                case 15 -> { in.readUnsignedByte(); in.readUnsignedShort(); }
                default -> throw new IllegalArgumentException("unsupported class constant");
            }
        }
        for (int i = 1; i < count; i++) {
            if (tags[i] == 7) checkClass((String) values[(Integer) values[i]]);
            // REST types in method/field/annotation descriptors may have no Class entry.
            if (tags[i] == 1) {
                var matcher = TYPE.matcher((String) values[i]);
                while (matcher.find()) checkClass(matcher.group(1));
            }
            if (tags[i] != 9 && tags[i] != 10 && tags[i] != 11) continue;
            int[] ref = (int[]) values[i];
            String owner = (String) values[(Integer) values[ref[0]]];
            if (!owner.startsWith(PREFIX)) continue;
            int[] signature = (int[]) values[ref[1]];
            String name = (String) values[signature[0]];
            String descriptor = (String) values[signature[1]];
            Class<?> type = load(owner);
            if (tags[i] == 9) {
                var field = type.getField(name);
                if (!field.getType().descriptorString().equals(descriptor)
                        || !Modifier.isPublic(field.getModifiers())) {
                    throw new NoSuchFieldException(owner + "." + name + descriptor);
                }
            } else {
                var methodType = MethodType.fromMethodDescriptorString(descriptor, RestLinkageCheck.class.getClassLoader());
                if (name.equals("<init>")) {
                    type.getConstructor(methodType.parameterArray());
                } else {
                    var method = type.getMethod(name, methodType.parameterArray());
                    if (!method.getReturnType().equals(methodType.returnType())) {
                        throw new NoSuchMethodException(owner + "." + name + descriptor);
                    }
                }
            }
            checked.add(owner + "." + name + descriptor);
        }
    }

    public static void main(String[] args) {
        try {
            if (args.length != 1) throw new IllegalArgumentException("need provider JAR");
            try (var jar = new JarFile(args[0])) {
                var entries = jar.entries();
                while (entries.hasMoreElements()) {
                    var entry = entries.nextElement();
                    if (entry.getName().endsWith(".class")) {
                        try (var stream = jar.getInputStream(entry)) { check(stream); }
                    }
                }
            }
            if (checked.isEmpty()) throw new IllegalStateException("no REST references checked");
            var api = load("jakarta/ws/rs/core/Response").getProtectionDomain().getCodeSource().getLocation();
            System.out.println("REST linkage OK: " + checked.size() + " references against " + Path.of(api.toURI()).getFileName());
            checked.stream().sorted().forEach(name -> System.out.println("REST reference: " + name));
        } catch (Exception | LinkageError failure) {
            // This scans build artifacts only; keep the denial distinguishable from launch failures.
            System.err.println("REST linkage mismatch: " + failure.getClass().getSimpleName());
            System.exit(1);
        }
    }
}
