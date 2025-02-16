import torch
import torch.nn as nn
import torch.nn.functional as F
class CrossAttention(nn.Module):
    def __init__(self, hidden_size, latent_size, cross_attn_heads):
        super().__init__()
        self.hidden_size = hidden_size
        self.num_heads = cross_attn_heads

        # Linear transformations for Q, K, V in cross-attention
        self.query_proj = nn.Linear(hidden_size, hidden_size)
        self.key_proj = nn.Linear(latent_size, hidden_size)
        self.value_proj = nn.Linear(latent_size, hidden_size)

        self.key_cache = None
        self.value_cache = None
        self.latent_vector_cache = None

        # Output projection
        self.out_proj = nn.Linear(hidden_size, hidden_size)

        self.scaling = (self.hidden_size // self.num_heads) ** -0.5

    def forward(self, hidden_states, latent_vector):
        batch_size, seq_len, _ = hidden_states.shape

        # update cache
        if self.latent_vector_cache is None or not torch.equal(self.latent_vector_cache, latent_vector):
            self.latent_vector_cache = latent_vector
            self.key_cache = self.key_proj(latent_vector)
            self.value_cache = self.value_proj(latent_vector)

        key = self.key_cache.unsqueeze(1).expand(-1, seq_len, -1)
        value = self.value_cache.unsqueeze(1).expand(-1, seq_len, -1)

        # Prepare Q
        query = self.query_proj(hidden_states)

        # Reshape for multi-head attention
        query = query.view(batch_size, seq_len, self.num_heads, self.hidden_size // self.num_heads).transpose(1, 2)
        key = key.view(batch_size, seq_len, self.num_heads, self.hidden_size // self.num_heads).transpose(1, 2)
        value = value.view(batch_size, seq_len, self.num_heads, self.hidden_size // self.num_heads).transpose(1, 2)

        # Scaled dot-product attention
        attn_output = F.scaled_dot_product_attention(query, key, value)

        # Reshape and project back
        attn_output = attn_output.transpose(1, 2).contiguous().view(batch_size, seq_len, self.hidden_size)
        attn_output = self.out_proj(attn_output)

        return attn_output


class CrossAttentionDecoderLayerWrapper(nn.Module):
    def __init__(self, original_layer, cross_attn_module, apply_cross_attn=False):
        super().__init__()
        self.original_layer = original_layer
        self.cross_attn = cross_attn_module
        self.apply_cross_attn = self.cross_attn != None

    def forward(self, hidden_states, latent_vector=None, use_cache=False, past_key_value=None, **kwargs):
        # Prepare kwargs for original layer
        layer_kwargs = {
            'use_cache': use_cache,
            'past_key_value': past_key_value
        }
        layer_kwargs.update(kwargs)
        # print(f"Layer kwargs: {layer_kwargs}")  # Debug print
        # Run original layer operations
        outputs = self.original_layer(
            hidden_states,
            **layer_kwargs
        )
        # print(f"Outputs type: {type(outputs)}")  # Debug print
        # print(f"Outputs structure: {outputs}")    # Debug print

        # if isinstance(outputs, tuple):
        #     print(f"Outputs length: {len(outputs)}")  # Debug print

        present_key_value = None
        if use_cache and len(outputs)>=2:
            hidden_states, present_key_value = outputs[:2]


        # Conditionally apply cross-attention
        if self.apply_cross_attn and latent_vector is not None:
            cross_attn_output = self.cross_attn(hidden_states, latent_vector)
            hidden_states = hidden_states + cross_attn_output

        if use_cache:
            return (hidden_states, present_key_value)
        return (hidden_states,)
