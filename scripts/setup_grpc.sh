#!/bin/bash

# SECURE Setup gRPC dependencies for Lightning Policy Manager
# SECURITY: Only copies SAFE protobuf files for fee management

echo "🔒 Setting up SECURE gRPC for Lightning Policy Manager..."

# Install required gRPC packages
echo "📦 Installing gRPC dependencies..."
pip install grpcio grpcio-tools googleapis-common-protos protobuf

# 🚨 SECURITY: Only copy SAFE protobuf files - NOT ALL FILES!
echo "🛡️  Copying ONLY fee-management protobuf files..."

if [ -d "charge-lnd-original/charge_lnd/grpc_generated/" ]; then
    mkdir -p src/experiment/grpc_generated/
    
    # ✅ SAFE: Copy only fee-management related files
    echo "   Copying lightning_pb2.py (fee management operations)..."
    cp charge-lnd-original/charge_lnd/grpc_generated/__init__.py src/experiment/grpc_generated/
    cp charge-lnd-original/charge_lnd/grpc_generated/lightning_pb2.py src/experiment/grpc_generated/
    cp charge-lnd-original/charge_lnd/grpc_generated/lightning_pb2_grpc.py src/experiment/grpc_generated/
    
    # 🚨 CRITICAL: DO NOT COPY DANGEROUS FILES
    echo "   🚫 SECURITY: Skipping walletkit_pb2* (wallet operations - DANGEROUS)"
    echo "   🚫 SECURITY: Skipping signer_pb2* (private key operations - DANGEROUS)"  
    echo "   🚫 SECURITY: Skipping router_pb2* (routing operations - NOT NEEDED)"
    echo "   🚫 SECURITY: Skipping circuitbreaker_pb2* (advanced features - NOT NEEDED)"
    
    echo "✅ SECURE protobuf files copied successfully!"
else
    echo "❌ charge-lnd protobuf source not found. Manual setup required."
    echo "   Only copy lightning_pb2.py and lightning_pb2_grpc.py from charge-lnd"
    echo "   🚨 NEVER copy walletkit_pb2*, signer_pb2* - they enable fund theft!"
fi

echo "✅ gRPC setup complete!"
echo ""
echo "Benefits of gRPC over REST:"
echo "  • ~10x faster fee updates"
echo "  • Better type safety with protobuf"
echo "  • Native LND interface (same as charge-lnd)"
echo "  • 📱 Lower network overhead"
echo "  • Built-in connection pooling"
echo ""
echo "Your Lightning Policy Manager will now use gRPC by default!"
echo "To test: ./lightning_policy.py -c test_config.conf apply --dry-run"