---
title: "Entropy coding by a beginner for beginners - Part 4: Basic PPM"
date: 2023-06-14 00:00:02 +0200
categories: [compression]
tags: [arithmetic coding, compression, PPM]
---

## About PPM

For extending the idea of context modeling shown in `SimpleOrder1AC`, we don’t need to invent anything. It was already done for us back in 1984 by the authors who laid down the idea of the PPM (Prediction by Partial Matching) algorithm [1].

In order to have some context for what we will be doing in this part, let’s consider what PPM represents. We will be discussing finite-context modeling, which means our model will hold a maximum of Order-N context, where N we set as a parameter at the initialization of the model. As a quick reminder, Order-N context means the number of preceding symbols that we have processed, which form the context for encoding the current symbol. In the case of `SimpleOrder1AC`, the context for the current symbol was formed by only one preceding symbol. So, we have a model and contexts of this model (CM). For each context from 0 to the N-th order that we encounter, we will create a CM of that order (the order of particular context will be denoted as CM(k)).

Similarly to `SimpleOrder1AC`, each CM will store a counter for every symbol encountered in that particular context. Based on these counters, we will estimate the probability of the symbol we are trying to encode. Since contexts are created dynamically, we will store all contexts and their corresponding data in a pre-allocated fixed-size memory pool. This helps to limit the maximum amount of memory that PPM can use. In other cases it can easily eat up all memory. To fit as many contexts as possible, we store only symbols that have appeared in each particular context.

For each symbol that we encoding, we are start by attempting to encode them in the highest available CM, as we can assume that the accumulated statistic in those contexts is most relevant for us, although not necessarily. If we encounter a symbol that has not appeared in the current context or if the context does not exist yet, we descend to a lower-order child context until we find a context where we can encode the current symbol. For example, if we have two context CM(2) \<oq\> and \<kq\>, they will share a common lower-order child context CM(1) \<q\>. If we have found a context but still need to descend to a child context due to a symbol miss, we must indicate this. This is necessary because we encode our symbol in context that is different from the current context. While encoding, it is obvious to us that the current context doesn’t have the required symbol, but during decoding, we only receive CDF values that are between CDF[low] and CDF[high] of the encoded symbol. We need to decode the received value unambiguously, and for this, we must be in the right context at that time. To signal to the decoder that it needs to descend to the child context, we use a special symbol whose value doesn’t belong to any of the symbols in our alphabet. This symbol is called an escape symbol (ESC).

The first context that we can have is CM(-1), where all symbols will have equal probability and won’t be changed after encoding from it. In this case, in CM(0), we can store only symbols that appear in it. Similarly, we can initialize all symbols for CM(0) at the beginning and use them. If we encode ESC in the first context (CM(-1) or CM(0)), we assume that it denotes the end-of-stream.

Below is an illustration of a possible context in the “abraabracadabra” text when encoding the last character ‘a’. In most examples I’ve seen a context tree is depicted from right to left. This doesn’t change the meaning, but since most of us imagine that we read our data from left to right from memory, it seemed to me that it would be easier to see how they are created from that point of view. 

![](/assets/img/post/etr-enc-4/abra.png){: w="600" h="900"}

## Initializing PPM

The struct that represents the data for the context and symbols of this context looks like this:

```
struct context;

#pragma pack(1)
struct context_data
{
    context* Next;
    u16 Freq;
    u8 Symbol;
};

struct context
{
    context_data* Data;
    context* Prev;
    u16 TotalFreq;
    u16 EscapeFreq;
    u16 SymbolCount;

    static constexpr u32 MaxSymbol = 255;
};
```

Each context has a pointer to an array of symbols that appear in it, a count of these symbols, and a pointer to the child context. `TotalFreq` not include in itself value of the `EscapeFreq` counter. The pointer `*Next` in `context_data` is exactly the pointer shown as a dashed line in the image above. This means that to get to CM(1) \<a\>, we need to find the character ‘a’ in CM(0) and follow the `Next` pointer to it.

The model’s data that we operate on then look like:

```
class PPMByte
{
    context_data_excl* Exclusion;
    context* StaticContext; // order -1
    context* Order0;
    context* LastUsed;

    u32* ContextSeq;
    find_context_result* ContextStack;

    u32 OrderCount;
    u32 CurrMaxOrder;
    u32 SeqLookAt;

public:
    StaticSubAlloc<32> SubAlloc;
    static constexpr u32 EscapeSymbol = context::MaxSymbol + 1;

    PPMByte(u32 MaxOrderContext, u32 MemLimit = 0) :
        SubAlloc(MemLimit), OrderCount(MaxOrderContext)
    {
        initModel();
    }
}
```
What each variable means we will see literally in the next two functions. That’s why I’ll hold the explanation for them until then. For now, we can see, as I mentioned before, that we limit the model’s memory usage and context depth at initialization. `StaticSubAlloc` is a simple allocator driven by a doubly linked list and can (probably must) be separated from the model at all.

```
void initModel()
{
    CurrMaxOrder = 0;

    StaticContext = SubAlloc.alloc<context>(1);
    ZeroStruct(*StaticContext);

    StaticContext->Data = SubAlloc.alloc<context_data>(256);
    StaticContext->EscapeFreq = 1;
    StaticContext->TotalFreq = 256;
    StaticContext->SymbolCount = 256;

    for (u32 i = 0; i < StaticContext->SymbolCount; ++i)
    {
        StaticContext->Data[i].Freq = 1;
        StaticContext->Data[i].Symbol = i;
        StaticContext->Data[i].Next = nullptr;
    }

    Exclusion = SubAlloc.alloc<context_data_excl>(1);
    clearExclusion();

    Order0 = SubAlloc.alloc<context>(1);
    ZeroStruct(*Order0);

    initContext(Order0, 0);
    Order0->Prev = StaticContext;

    // last encoded symbols
    ContextSeq = SubAlloc.alloc<u32>(OrderCount);

    // max symbol seq + context for that seq
    ContextStack = SubAlloc.alloc<find_context_result>(OrderCount + 1);
}
```

During the encoding/decoding of the first few symbols, we don’t have any contexts yet with a length of `OrderCount` to determine how many previous symbols we can use for context searching. To keep track of the current max depth, we use `CurrMaxOrder`, which is initially set to 0. The previous symbols are stored in the `ContextSeq` array, where the oldest symbol encountered is stored under index 0 and the symbol for CM(N) is stored under the index `CurrMaxOrder – 1`. Our CM(-1) is represented by `StaticContext`, where the frequency of each symbol will always be 1. We also initialize the Order0 context at the beginning so that we don’t have to check it every time we access it, as every search of CM(k) context starts from CM(0). Initialization symbol 0 in CM(0) also allows us to eliminate some edge checks during execution.

Initializing the context as follows:

```
b32 initContext(context* Context, u32 Symbol)
{
    Assert(Context);
    ZeroStruct(*Context);

    b32 Result = false;

    Context->Data = SubAlloc.alloc<context_data>(2);
    if (Context->Data)
    {
        Context->TotalFreq = 1;
        Context->EscapeFreq = 1;
        Context->SymbolCount = 1;

        context_data* Data = Context->Data;
        Data->Freq = 1;
        Data->Symbol = Symbol;
        Data->Next = nullptr;

        Result = true;
    };

    return Result;
}
```

We allocate space for two symbols at once during initialization to reduce the number of allocations and fragmentation. If `Context->Data` is equal to `nullptr`, it means that the allocator couldn’t find free space for the requested size anymore. In this situation, we reset the state of our model and allocator.

```
void reset()
{
    SubAlloc.reset();
    initModel();
}
```

This means that in general, it is necessary to check every allocation even during the execution of `initModel()`, or at least set a minimum memory pool size, but I didn’t do it because this is just test code. The struct for `context_data_excl` is an array in which we mark the presence of those symbols that we saw in parent context while we go down through child contexts.

```
struct context_data_excl
{
    u16 Data[256];
    static constexpr u16 Mask = MaxUInt16;
}; 

inline void clearExclusion()
{
    MemSet(&Exclusion->Data[0], ArrayCount(Exclusion->Data), context_data_excl::Mask);
}
```

We will very soon get back to the exclusion array since the next thing we will discuss is how we do encoding.

## Encoding

### Context search loop

```
void encode(ArithEncoder& Encoder, u32 Symbol)
{
    SeqLookAt = 0;
    u32 OrderLooksLeft = CurrMaxOrder + 1;

    context* Prev = 0;
    while (OrderLooksLeft)
    {
        find_context_result Find = {};

        if (Prev)
        {
            Find.Context = Prev;
        }
        else
        {
            findContext(Find);
        }

        if (!Find.IsNotComplete)
        {
            ...//encode symbol, if success than break from loop
        }

        ContextStack[SeqLookAt++] = Find;
        OrderLooksLeft--;
    }

    if (!OrderLooksLeft)
    {
        ...//encode СM(-1)
    }

    ...//update model

    clearExclusion();
}
```

One variable that was not mentioned in `initModel()` is `SeqLookAt`. We always set it to 0 at the start of the symbol encoding process because it serves as a point from which symbol we should start searching for the context in the `ContextSeq` array. Next, in the loop, we look for the context in which we will encode the symbol. We perform the search in the loop so that if the search for the current CM(k) context fails (symbol miss or such context just doesn’t exist yet), we can start searching again for CM(k - 1) starting from `ContextSeq[SeqLookAt + 1]`. If the searched CM(k) context has not yet been built, which is indicated by `Find.IsNotComplete`, then we don’t need to send ESC because the decoder won’t have this context either, and we simply store the result of this search in the `ContextStack` so that we can later build the missed context branch inside `update()`. The structure for the search result looks like this:

```
struct find_context_result
{
    context* Context;
    u16 SeqIndex;
    u16 ChainMissIndex;
    b16 IsNotComplete;
    b16 SymbolMiss;
};
```

When looking for the desired context, we try to follow the chain of pointers `context_data->Next` for the symbols stored in `ContextSeq` starting from `SeqLookAt`. That means if we didn’t find the context for CM(3) \<abc\>, then we search for CM(2) \<bc\>, not for \<ab\>.

```
void findContext(find_context_result& Result)
{
    context* CurrContext = Order0;

    u32 LookAtOrder = SeqLookAt; // from
    while (LookAtOrder < CurrMaxOrder)
    {
        u32 SymbolAtContext = ContextSeq[LookAtOrder];

        Assert(SymbolAtContext < 256);
        Assert(CurrContext->Data)

        symbol_search_result Search = findSymbolIndex(CurrContext, SymbolAtContext);
        if (!Search.Success)
        {
            Result.SymbolMiss = true;
            break;
        };

        context_data* Data = CurrContext->Data + Search.Index;
        if (!Data->Next)
        {
            Result.ChainMissIndex = Search.Index;
            break;
        }

        CurrContext = Data->Next;
        LookAtOrder++;
    }

    Result.Context = CurrContext;
    Result.SeqIndex = LookAtOrder;
    Result.IsNotComplete = CurrMaxOrder - LookAtOrder;
}
```

First, in each context, we are searching for the symbol to move to the next context. 

```
struct symbol_search_result
{
    b32 Success;
    u32 Index;
};

symbol_search_result findSymbolIndex(context* Context, u32 Symbol)
{
    symbol_search_result Result = {};

    for (u32 i = 0; i < Context->SymbolCount; ++i)
    {
        if (Context->Data[i].Symbol == Symbol)
        {
            Result.Index = i;
            Result.Success = true;
            break;
        }
    }

    return Result;
}
```

After that, we can check if this symbol has a pointer to the next context or not. Saving `CurrContext` and `LookAtOrder` in the result is also needed for execution of `update()` so that we can know from where to what point is need to complete the context. In the case when `CurrMaxOrder != LookAtOrder`, the value of `SymbolMiss` signals that we have a symbol miss on some branch during the context search process, and it’s not related to the miss of the actual symbol that we are looking for.

Up to this point, I have mentioned the `update()` function several times but haven’t explained it yet. This may have left some aspects vague for you, but please bear with me because understanding what happens during the lookup and how we fill the `ContextStack`, which `update()` relies on, will make it easier to comprehend what's going on inside it.

Let’s assume that we have found the context that we need. Now we can try to encode the symbol if it is present in the context or encode ESC otherwise.

```
void encode(ArithEncoder& Encoder, u32 Symbol)
{
    ...// init values
    context* Prev = 0;
    while (OrderLooksLeft)
    {
        find_context_result Find = {};
        
        ...// try to find context

        if (!Find.IsNotComplete)
        {
            Assert(Find.Context->TotalFreq);

            b32 Success = encodeSymbol(Encoder, Find.Context, Symbol);
            if (Success)
            {
                Assert(Find.Context->TotalFreq);
                LastUsed = Find.Context;
                break;
            }

            Prev = Find.Context->Prev;
            updateExclusionData(Find.Context);
        }

        ContextStack[SeqLookAt++] = Find;
        OrderLooksLeft--;
    }

    if (!OrderLooksLeft)
    {
        ...//encode СM(-1)
    }

    ...// update
    clearExclusion();
}
```

The `encodeSymbol()` function is a wrapper that returns `true` or `false` depending on whether the symbol was encoded or ESC. In the first case, we finish our task and can exit the loop, saving the context we used in `LastUsed` which will be needed in the `update()`. If we were unlucky and had to encode ESC inside `encodeSymbol()`, we saved the pointer to the child context and started the search again. The last step before searching in the child context is to mask all the symbols that we have seen.

```
void updateExclusionData(context* Context)
{
    context_data* ContextData = Context->Data;
    for (u32 i = 0; i < Context->SymbolCount; ++i)
    {
        context_data* Data = ContextData + i;
        Exclusion->Data[Data->Symbol] = 0;
    }
}
```

All symbols that are to be counted will have a mask of 0xFFFF and 0 if we are ignoring them. The reason for doing this is that all symbols that belong to context CM(k) are also included in the child CM(k - 1). Thus, when calculating CDF[low] and CDF[high] for the current symbol, we can exclude them, thereby increasing the range for the remaining symbols.

![](/assets/img/post/etr-enc-4/mask.png)

### Setting Prob struct

`encodeSymbol()` as I said before is just a wrapper.

```
b32 encodeSymbol(ArithEncoder& Encoder, context* Context, u32 Symbol)
{
    Assert(Context->EscapeFreq);
    prob Prob = {};

    b32 Success = getEncodeProb(Context, Prob, Symbol);
    Encoder.encode(Prob);

    return Success;
} 
```

Inside, we receive a `prob` struct that has been filled and then pass it to AC. Calculating the necessary values to fill `prob` for encoding and decoding is similar to how it was done in `SimpleOrder1AC`. However, now we must also handle the following cases: 
- the count of symbols can change for the context.
- symbols can be masked.
- special ESC symbol.

```
b32 getEncodeProb(context* Context, prob& Prob, u32 Symbol)
{
    b32 Result = false;

    u32 CumFreqLo = 0;
    u32 SymbolIndex = 0;
    for (; SymbolIndex < Context->SymbolCount; ++SymbolIndex)
    {
        context_data* Data = Context->Data + SymbolIndex;
        if (Data->Symbol == Symbol) break;

        CumFreqLo += Data->Freq & Exclusion->Data[Data->Symbol];
    }

    Prob.lo = CumFreqLo;
    if (SymbolIndex < Context->SymbolCount)
    {
        ...// calculate Prob.hi, update Symbol freq and TotalCount
        Result = true;
    }
    else
    {
        Prob.hi = Prob.scale = Prob.lo + Context->EscapeFreq;
    }

    return Result;
}
```

From the beginning, we start searching for the symbol that we need while simultaneously calculating CDF[low] along the way. Just as a reminder, CDF[low] is equal to the sum of all symbol frequencies that came before the symbol that we are looking for. That’s why we break from the loop after finding it. Symbols that should not be counted are handled by performing a bitwise AND with their corresponding value in the `Exclusion->Data` array. This operation simply returns 0 if the symbol has been masked, keeping `CumFreqLo` unchanged.

After that, we either have found the symbol or not. Let’s first take a look at the case when we haven’t found the symbol that we need in the context (as it’s just a few lines of code). In that case, we need to encode ESC. If we haven’t made `break` from the loop, then `CumFreqLo` already holds the sum of frequency for all symbols that were not masked out in the current context. But we count our last symbol as being ESC. That means, to have the ability to unambiguously decode every symbol, our Prob.scale must look like below, if we didn’t mask out any symbol (that’s a case for encoding from CM(N)).

```
Prob.scale = Context->TotalCount + Context->EscapeFreq;
```

And the values of `Prob.lo` and `Prob.hi` will be somewhere in the range of the `Prob.scale` value. Because ESC is the last symbol of our working alphabet, when encoding it, `Prob.hi == Prob.scale`. For now, we assume that `Context->EscapeFreq` always equals 1, meaning it stays the same after a call of `initContext()`.

If we have found the symbol, then we can immediately calculate its `Prob.hi`, but we still need to finish calculation of `Prob.scale`.

```
b32 getEncodeProb(context* Context, prob& Prob, u32 Symbol)
{
    for (; SymbolIndex < Context->SymbolCount; ++SymbolIndex)
    ...// calculate CumFreqLo

    Prob.lo = CumFreqLo;
    if (SymbolIndex < Context->SymbolCount)
    {
        context_data* MatchSymbol = Context->Data + SymbolIndex;
        Prob.hi = Prob.lo + MatchSymbol->Freq;

        u32 CumFreqHi = Prob.hi;
        for (u32 i = SymbolIndex + 1; i < Context->SymbolCount; ++i)
        {
            context_data* Data = Context->Data + i;
            CumFreqHi += Data->Freq & Exclusion->Data[Data->Symbol];
        }

        Prob.scale = CumFreqHi + Context->EscapeFreq;

        MatchSymbol->Freq += 1;
        Context->TotalFreq += 1;

        if (Context->TotalFreq >= FREQ_MAX_VALUE)
        {
            rescale(Context);
        }

        Result = true;
    }
    else
    {
        Prob.hi = Prob.scale = Prob.lo + Context->EscapeFreq;
    }

    return Result;
}
```

For finishing `Prob.scale`, we do the same stuff as for `Prob.lo` at the beginning. However, this time we must start from `SymbolIndex + 1` and go to the end of the array. Also, this time we don’t need to do checks inside the body of the loop. Currently, it turns out that if we encode our symbol in CM(N) in which `Exclusion->Data` has not been modified yet at all, we are spending CPU time executing operation with `Exclusion->Data`. This is certainly a drawback, and we will fix it later.

The limit on the maximum value of CDF has not disappeared anywhere and is still equal to `FREQ_MAX_VALUE`, after exceeding which we do the same as in `SimpleOrder1AC`.

```
void rescale(context* Context)
{
    Context->TotalFreq = 0;
    for (u32 i = 0; i < Context->SymbolCount; ++i)
    {
        context_data* Data = Context->Data + i;
        u32 NewFreq = (Data->Freq + 1) / 2;
        Data->Freq = NewFreq;
        Context->TotalFreq += NewFreq;
    }
}
```

### Encoding in CM(-1)

After all these operations in the context search loop, when we have already broken from it, we do a check to see if we have encoded the symbol at least in CM(0) and if it should be encoded in CM(-1).

```
void encode(ArithEncoder& Encoder, u32 Symbol)
{
    SeqLookAt = 0;
    u32 OrderLooksLeft = CurrMaxOrder + 1;

    context* Prev = 0;
    while (OrderLooksLeft)
    {
        ...// try to encode _Symbol_ in context > CM(-1)
    }

    if (!OrderLooksLeft)
    {
        ...//encode in CM(-1)
        LastUsed = StaticContext;

        prob Prob = {};
        b32 Success = getEncodeProb(StaticContext, Prob, Symbol);

        // StaticContext->Data[Symbol].Freq -= 1;
        // StaticContext->TotalFreq -= 1;

        Assert(Success);
        Assert(SeqLookAt);

        Encoder.encode(Prob);
    }

   ...// update
    clearExclusion();
}
```

For encoding in CM(-1), we use `getEncodeProb()` and subtract 1 from the encoded symbol so that `StaticContext` remains unchanged because inside `getEncodeProb()` we have incremented it. However, we can actually omit the subtraction because during the execution of `getEncodeProb()` we mask symbols with their corresponding values in `Exclusion->Data`. This means that every symbol that was absent in CM(0) and then encoded in CM(-1) after `update()` execution will be added to CM(0) and will be masked at the next time we encode from CM(-1).

Again this mystical `update()` function comes. We finally reached it.

## Update context tree

### Big picture

```
void encode(ArithEncoder& Encoder, u32 Symbol)
{
    ...//encode symbol

    update(Symbol);
    updateOrderSeq(Symbol);

    clearExclusion();
}
```

The last thing before leaving `encode()` is to build all missing context branches inside `update()` and update `ContextSeq` in `updateOrderSeq()`. `update()` is quite extensive, so let’s start by understanding what it does in general and then consider each part separately to avoid taking up too much space in an already bloated post.

```
void update(u32 Symbol)
{
    context* Prev = LastUsed;

    u32 ProcessStackIndex = SeqLookAt;
    for (; ProcessStackIndex > 0; --ProcessStackIndex)
    {
        find_context_result* Update = ContextStack + (ProcessStackIndex - 1);
        context* ContextAt = Update->Context;

        if (Update->IsNotComplete)
        {
            ...// get context from which we will start build

            if (Update->SymbolMiss)
            {
                ...
            }
            else
            {
                ...
            }
            ...// construct non exist branch of context
            ...// init context for wich we build this path
        }
        else
        {
            ...// only add symbol to context
        }

        ContextAt->Prev = Prev;
        Prev = ContextAt;
    }

    if (ProcessStackIndex)
    {
        // memory not enough, restart model
        reset();
    }
}
```

Let’s consider this by example. Assuming that the maximum context depth is 3. While searching for CM(3) \<abc\>, we discovered that the branch for this context starting from the first symbol ‘a’ is missing. We saved this search result in `ContextStack[0]`. After that we couldn't find child CM(2) \<bc\> for the same reason and saved it in `ContextStack[1]`. However, CM(1) \<c\> is present but we couldn't find the symbol that we needed inside it, so it also goes to `update()` in `ContextStack[2]`.

At the time of executing `update()`, we start building context from the lowest order CM, which is currently CM(1) \<c\>. We simply need to add the symbol to it as indicated by `Update->IsNotComplete == false`, and save it as `Prev`. This allows us to set it as the child context for the next CM(2) \<bc\>. It’s possible that you might be confused with all these connections between contexts, as I was too. It may not be obvious why we can’t just construct CM(3) \<abc\> and set each preceding context as a child. We can’t do this because in this implementation, each branch of contexts is representing a chain of parent contexts and child contexts will be located actually on a different branch (although “child” and “parent” are kind of wrong naming for this).

![](/assets/img/post/etr-enc-4/branches.png)

As you can see from the image above, if we set CM(3) \<abc\> as the child for CM(2) \<ab\> after building it, it would be incorrect. The correct choice must be CM(2) \<bc\>.

### Add missed symbol

When adding a symbol to the context we do this:

```
b32 addSymbol(context* Context, u32 Symbol)
{
    b32 Result = false;

    u32 PreallocSymbol = getContextDataPreallocCount(Context);
    Context->Data = SubAlloc.realloc(Context->Data, ++Context->SymbolCount, PreallocSymbol);

    if (Context->Data)
    {
        context_data* Data = Context->Data + (Context->SymbolCount - 1);
        Data->Freq = 1;
        Data->Symbol = Symbol;
        Data->Next = nullptr;

        Context->TotalFreq += 1;

        Result = true;
    }

    return Result;
}

void update(u32 Symbol)
{
    context* Prev = LastUsed;

    u32 ProcessStackIndex = SeqLookAt;
    for (; ProcessStackIndex > 0; --ProcessStackIndex)
    {
        find_context_result* Update = ContextStack + (ProcessStackIndex - 1);
        context* ContextAt = Update->Context;

        if (Update->IsNotComplete)
        {
            ...// complete branch
        }
        else
        {
            Assert(ContextAt->Data);
            if (!addSymbol(ContextAt, Symbol)) break;
        }

        ContextAt->Prev = Prev;
        Prev = ContextAt;
    }

    ...//reset if memory not enough
}
```

In this case, `SubAlloc.realloc()` will perform reallocation only if we have exceeded the limit of available memory for the previously allocated block. It will ignore the value of `PreallocSymbol` if this block still has enough memory. For example, since previously we have allocated memory for 2 `context_data` structs, when adding the second symbol to the context, `SubAlloc.realloc()` will immediately return the pointer that was passed as the first argument to it. This behavior of the `realloc` function may not always be desirable, but it works for us. Next, we initialize the symbol, taking into account that `Context->TotalFreq` has increased, and then return the result.

### Complete context branch

In the case when we need to complete the missed branch, we first need to obtain the `context_data*` from which we will start doing it.

```
void update(u32 Symbol)
{
    context* Prev = LastUsed;

    u32 ProcessStackIndex = SeqLookAt;
    for (; ProcessStackIndex > 0; --ProcessStackIndex)
    {
        find_context_result* Update = ContextStack + (ProcessStackIndex - 1);
        context* ContextAt = Update->Context;

        if (Update->IsNotComplete)
        {
            context_data* BuildContextFrom = nullptr;

            if (Update->SymbolMiss)
            {
                if (!addSymbol(ContextAt, ContextSeq[Update->SeqIndex])) break;

                BuildContextFrom = ContextAt->Data + (ContextAt->SymbolCount - 1);
            }
            else
            {
                BuildContextFrom = ContextAt->Data + Update->ChainMissIndex;
            }

            ...// construct non exist branch of context
            ...// init context for wich we build this path
        }
        else
        {
            Assert(ContextAt->Data);
            if (!addSymbol(ContextAt, Symbol)) break;
        }

        ContextAt->Prev = Prev;
        Prev = ContextAt;
    }

    ...//reset if memory not enough
}
```

At this stage, we either need to add the missing symbol `ContextSeq[Update->SeqIndex]` to the context, where it automatically becomes the last in the array, so we obtain it as `ContextAt->SymbolCount – 1`, or simply move to the symbol at the index `Update->ChainMissIndex`. After that, we complete the missing branch of the context starting from `BuildContextFrom`.

```
context* allocContext(u32 Symbol)
{
    context* New = SubAlloc.alloc<context>(1);
    if (New)
    {
        ZeroStruct(*New);
        if (!initContext(New, Symbol))
        {
            New = nullptr;
        }
    }

    return New;
}

void update(u32 Symbol)
{
    context* Prev = LastUsed;

    u32 ProcessStackIndex = SeqLookAt;
    for (; ProcessStackIndex > 0; --ProcessStackIndex)
    {
        find_context_result* Update = ContextStack + (ProcessStackIndex - 1);
        context* ContextAt = Update->Context;

        if (Update->IsNotComplete)
        {
            ...// set BuildContextFrom

            u32 SeqAt = Update->SeqIndex + 1;
            for (; SeqAt < CurrMaxOrder; SeqAt++)
            {
                context* Next = allocContext(ContextSeq[SeqAt]);
                if (!Next) break;
        
                ContextAt = BuildContextFrom->Next = Next;
                BuildContextFrom = &ContextAt->Data[0];
            }

            if (SeqAt != CurrMaxOrder) break;

            context* EndSeqContext = allocContext(Symbol);
            if (!EndSeqContext) break;

            ContextAt = BuildContextFrom->Next = EndSeqContext;
        }
        else
        {
            Assert(ContextAt->Data);
            if (!addSymbol(ContextAt, Symbol)) break;
        }

        ContextAt->Prev = Prev;
        Prev = ContextAt;
    }

    ...// reset
}
```

Let’s look at what’s happening here using СM(3) \<abc\> from the picture above. If the context is completely missed, this means that the symbol ‘a’ hasn’t even appeared in CM(0) yet, then `Update->SeqIndex` will be equal to 0. With the previous step, we created symbol ‘a’ in CM(0), which means the next step should start from `Update->SeqIndex + 1`, that is, from symbol ‘b’. On the first iteration we create CM(1) \<a\> with a single symbol ‘b’ in it. On the second iteration, we create CM(2) \<ab\> that has the symbol ‘c’ in it, which `BuildContextFrom` is pointing to after this iteration is complete. After we finish this loop, we check `SeqAt != To` to ensure that all needed context on the way was built. If everything is okay, we initialize for CM(3) \<abc\> with the symbol that we have passed to `update()`. 

```
void update(u32 Symbol)
{
    context* Prev = LastUsed;

    u32 ProcessStackIndex = SeqLookAt;
    for (; ProcessStackIndex > 0; --ProcessStackIndex)
    {
        find_context_result* Update = ContextStack + (ProcessStackIndex - 1);
        ...// build context tree
    }

    if (ProcessStackIndex)
    {
        // memory not enough, restart model
        reset();
    }
}
```

If `ProcessStackIndex != 0`, it means we didn’t have enough memory to process all the ContextStack elements, and we made an early break from the update loop. In this case, we call `reset()` and finish `update()`. At the very end, we need to update the list of the last characters we saw.

### Change current context

```
inline void updateOrderSeq(u32 Symbol)
{
    u32 UpdateSeqIndex = CurrMaxOrder;

    if (CurrMaxOrder == OrderCount)
    {
        UpdateSeqIndex--;

        for (u32 i = 0; i < (OrderCount - 1); ++i)
        {
            ContextSeq[i] = ContextSeq[i + 1];
        }
    }
    else
    {
        CurrMaxOrder++;
    }

    ContextSeq[UpdateSeqIndex] = Symbol;
}
```

If we are not reaching the limit of the previous symbol that we can store, we simply write each new symbol to the next free place in `ContextSeq`. In the other case, we shift symbols to make room for a new one.

## Decoding

### Context search loop

The decoding process differs only in the fact that now we attempt to find the required symbol by obtaining its value between CDF[low] and CDF[high]. The algorithm for getting a symbol from its CDF value will be similar to `SimpleOrderAC::getSymbolFromFreq()` from the previous part.

The body of the decoding function that the user uses is nearly identical to `encode()`, so I only show differences between them to save space.

```
struct decode_symbol_result
{
    prob Prob;
    u32 Symbol;
};

u32 decode(ArithDecoder& Decoder)
{
    u32 ResultSymbol;
    ...
    context* Prev = 0;
    while (OrderLooksLeft)
    {
        ...// try to find context

        if (!Find.IsNotComplete)
        {
            Assert(Find.Context->TotalFreq)
            b32 Success = decodeSymbol(Decoder, Find.Context, &ResultSymbol);
            ... // break if success == true
        }
        ...
    }

    if (!OrderLooksLeft)
    {
        //decode in CM(-1)

        LastUsed = StaticContext;
        decode_symbol_result DecodedSymbol = getSymbolFromFreq(Decoder, StaticContext);
        ResultSymbol = DecodedSymbol.Symbol;

        // if it is not end of stream
        if (ResultSymbol != EscapeSymbol)
        {
            Assert(SeqLookAt);
            Decoder.updateDecodeRange(DecodedSymbol.Prob);
        }
    }

    ...//udpate    
    return ResultSymbol;
}
```

In the loop of context searching, instead of `encodeSymbol()`, we use `decodeSymbol()` which after the decoding of a regular symbol stores it to `ResultSymbol`. If we encounter ESC during decoding in CM(-1), it indicates the end of the encoded stream, and as before, we assume that there will be no more data, so we don’t invoke `updateDecodeRange()`.

### Decode obtained frequency

The `decodeSymbol()` function is also created for convenience, and nothing special happens inside it.

```
b32 decodeSymbol(ArithDecoder& Decoder, context* Context, u32* ResultSymbol)
{
    b32 Success = false;

    decode_symbol_result Decoded = getSymbolFromFreq(Decoder, Context);
    Decoder.updateDecodeRange(Decoded.Prob);

    if (Decoded.Symbol != EscapeSymbol)
    {
        Success = true;
        *ResultSymbol = Decoded.Symbol;
    }

    return Success;
}
```

What is more interesting is what happens inside `getSymbolFromFreq()`.

```
decode_symbol_result getSymbolFromFreq(ArithDecoder& Decoder, context* Context)
{
    decode_symbol_result Result = {};

    Result.Prob.scale = getExcludedTotal(Context) + Context->EscapeFreq;
    u32 DecodeFreq = Decoder.getCurrFreq(Result.Prob.scale);

    ...// decode freq

    return Result;
}
```

We can’t start searching for a symbol until we perform `getCurrFreq()`. To obtain the correct value from it, we need to correctly determine with respect to which `Prob.scale` value the symbol was encoded. During encoding, we did it like this:

```
context_data* Data = Context->Data + i;
Data->Freq & Exclusion->Data[Data->Symbol];
```

This means that the value of `Prob.scale` may not have been equal to `Context->TotalCount + Context->EscapeFreq`. Thus, we first need to obtain the current sum of `TotalCount`, taking into account masked frequencies, and then add it to `EscapeFreq`, which was always accounted for during encoding.

```
u32 getExcludedTotal(context* Context)
{
    u32 Result = 0;
    for (u32 i = 0; i < Context->SymbolCount; ++i)
    {
        context_data* Data = Context->Data + i;
        Result += Data->Freq & Exclusion->Data[Data->Symbol];
    }

    return Result;
}
```

Yes, we simply perform the operation that we are already familiar with, but for all symbols, in order to later do almost the same thing again!

```
decode_symbol_result getSymbolFromFreq(ArithDecoder& Decoder, context* Context)
{
    decode_symbol_result Result = {};

    Result.Prob.scale = getExcludedTotal(Context) + Context->EscapeFreq;
    u32 DecodeFreq = Decoder.getCurrFreq(Result.Prob.scale);

    u32 CumFreq = 0;
    u32 SymbolIndex = 0;
    for (; SymbolIndex < Context->SymbolCount; ++SymbolIndex)
    {
        context_data* Data = Context->Data + SymbolIndex;
        CumFreq += Data->Freq & Exclusion->Data[Data->Symbol];

        if (CumFreq > DecodeFreq) break;
    }

    if (SymbolIndex < Context->SymbolCount)
    {
        ...//calculate prob struct for regular symbol
    }
    else
    {
        ...//calculate prob struct for ESC symbol
    }

    return Result;
}
```

We do the same thing as in `SimpleOrder1AC::getSymbolFromFreq()`, but now we also mask each symbol. Another approach, which may seem more correct, is to iterate through `Context->Data` once, calculating `TotalCount` with `Exclusion` taken into account, and during that process recoding the index or pointer to the nonmasked symbols in an array. Then, iterate only through these symbols to find `CumFreq > DecodeFreq` (you will find an example inside the commit for this part). This also makes sense! For data that compresses well and has a small `SymbolCount`, I didn’t observe a difference in execution speed. However, for data with poor context dependencies, the approach from the example above is faster.

![](/assets/img/post/etr-enc-4/utill1.png)
_shown approach for poor context data_

![](/assets/img/post/etr-enc-4/utill2.png)
_described approach for poor context data_

Here “Cycles of N Ports” indicates, as Intel states in the tooltip, the fraction of time when the CPU performs N uops in one cycle, rather than the specific ports on which the uop instructions are executed, which you could see [here](https://uops.info/table.html). A classic illustration of CPU’s OOO. Maybe on older CPUs, this approach would have a greater impact on executing speed. Not sure which method is best for PPM style of data, I just decided to make a measure from curiosity reason and show it to you.

```
decode_symbol_result getSymbolFromFreq(ArithDecoder& Decoder, context* Context)
{
    decode_symbol_result Result = {};

    ...// search CDF[high] of symbol

    if (SymbolIndex < Context->SymbolCount)
    {
        context_data* MatchSymbol = Context->Data + SymbolIndex;
            
        Result.Prob.hi = CumFreq;
        Result.Prob.lo = CumFreq - MatchSymbol->Freq;
        Result.Symbol = MatchSymbol->Symbol;

        MatchSymbol->Freq += 1;
        Context->TotalFreq += 1;

        if (Context->TotalFreq >= FREQ_MAX_VALUE)
        {
            rescale(Context);
        }
    }
    else
    {
        Result.Prob.hi = Result.Prob.scale;
        Result.Prob.lo = Result.Prob.scale - Context->EscapeFreq;
        Result.Symbol = EscapeSymbol;
    }

    return Result;
}
```

Since we have already calculated `Prob.scale`, there is no need to calculate anything further except for the values `Prob.hi` and `Prob.lo`. In the case where we have found the symbol that we need, `CumFreq` stores the value of CDF[high], so we simply subtract the symbol’s frequency value from it to obtain CDF[low]. In the case of an ESC symbol, `Prob.scale == Prob.hi`, and to obtain `Prob.lo`, we simply subtract the `EscapeFreq` value.

## Encoding EOS

And finally, the last thing is encoding the end of the stream. We could do this by simply passing ESC to the `encode()` function, but we can perform an optimization that no one asked for by throwing away the extra code for such a case and writing it like this:

```
void encodeEndOfStream(ArithEncoder& Encoder)
{
    u32 OrderIndex = SeqLookAt = 0;

    context* EscContext = 0;
    u32 OrderLooksLeft = CurrMaxOrder + 1;
    while (OrderLooksLeft)
    {
        find_context_result Find = findContext();

        if (!Find.IsNotComplete)
        {
            EscContext = Find.Context;
            break;
        }

        SeqLookAt++;
        OrderLooksLeft--;
    }

    while (EscContext->Prev)
    {
        encodeSymbol(Encoder, EscContext, EscapeSymbol);
        updateExclusionData(EscContext);

        Assert(EscContext->Prev)
        EscContext = EscContext->Prev;
    }

    prob Prob = {};
    getEncodeProb(StaticContext, Prob, EscapeSymbol);
    Encoder.encode(Prob);
}
```

The idea is to generate a sequence of ESC symbols from the last context that the decoder has up to CM(-1). Since in the context search loop, non-existing contexts do not generate an ESC symbol, we are looking for the first complete branch of context and descending to the bottom. In this sequence, only CM(-1) should have `EscContext->Prev == nullptr`.

## Result

To demonstrate the result, in addition to the standard files, I also added the Intel Manual to slightly disappoint those who are seeing PPM for the first time. I didn’t add it to the repository to avoid bloating it. Additionally, we can see how many bytes were spent on encoding actual symbols and how many were spent on ESC. Their sum may not match the size of the encoded file, as I calculated the “ideal encoded length” that AC should have achieved. Compression was performed with a memory limit of 10 MiB and Order-4 simply because this depth showed the best result.

| name    |   H   | file size | compr. size |  bpb  | Sym       | ESC        |
| :------ | :---- | :-------- | :---------- | :---- | :---------| :--------- |
| book1   | 4.572 |    768771 | 224214      | 2.333 |  183212.3 | 40998.7    |
| geo     | 5.646 |    102400 | 78287       | 6.116 |  47711.5  | 30574.4    |
| obj2    | 6.26  |    246814 | 86715       | 2.81  |  60492.6  | 26220.8    |
| pic     | 1.21  |    513216 | 56116       | 0.875 | 40884.3   | 15178.9    |
|Intel.pdf| 7.955 | 26192768  | 34347683    | 10.49 | 21248478.7| 13097916.2 |

All previous files become smaller, but given the fact that Intel.pdf becomes larger, it’s not very impressive. “What did we spend time for!?” Somebody might have thought. As we can see, we were able to compress the file actually, but the portion of ESC symbols is indeed high. The reason is that we have encoded the ESC symbols using the PPMA method, and the actual probability of exiting the context had the following form:

```TEXT
s – the total sum of all symbol's frequency in the context;
1/(1 + s) 
```

It’s cool that we provide a wider range for encoding regular symbols, but as a result, when using PPM for data without stable contextual dependencies, it can has drawbacks. In fact, PPM is not suitable for such data at all, but we still can improve our results. We will skip the PPMB method and directly look at PPMC, which essentially has the following form.

```TEXT
u – count of unique symbols in context;
s – the total sum of all symbol's frequency in the context;
u/(s + u)  
```

This formula means that we must increment `EscapeFreq` each time when we add a new symbol to the context.

```
b32 addSymbol(context* Context, u32 Symbol)
{
    b32 Result = false;

    u32 PreallocSymbol = getContextDataPreallocCount(Context);
    Context->Data = SubAlloc.realloc(Context->Data, ++Context->SymbolCount, PreallocSymbol);

    if (Context->Data)
    {
        context_data* Data = Context->Data + (Context->SymbolCount - 1);
        Data->Freq = 1;
        Data->Symbol = Symbol;
        Data->Next = nullptr;

        Context->TotalFreq += 1;
        Context->EscapeFreq += 1; // now incrementing

        Result = true;
    }

    return Result;
}
```

Checking result:

| name      |   H   | file size | compr. size |  bpb  | Sym       | ESC        |
| :-------- | :---- | :-------- | :---------- | :---- | :---------| :--------- |
| book1     | 4.572 |    768771 | 223937      | 2.33  |  203145.2 | 20788.1    |
| geo       | 5.646 |    102400 | 61108       | 4.774 |  51439.6  | 9667       |
| obj2      | 6.26  |    246814 | 77446       | 2.51  |  66454    | 10998.4    |
| pic       | 1.21  |    513216 | 52486       | 0.818 | 45292.7   | 7141.5     |
| Intel.pdf | 7.955 | 26192768  | 25331611    | 7.737 | 22122485.9| 3207770.4  |

Nice. We cannot ignore the encoding of ESC and need to find a balance somehow.

So we have finished the introduction to PPM. The main drawback at the moment is the context search process. Most of the time is spent in the `findSymbolIndex()` function. In the next part, we will see how it can be removed entirely.

[Source code](https://github.com/Akreson/compression_tests/tree/b563af268dc87ff93cbe77b1f0817c2a25f8b971) for this part.

## References

\[1\] Data Compression Using Adaptive Coding and Partial String Matching [https://www.researchgate.net/publication/2475970_Data_Compression_Using_Adaptive_Coding_and_Partial_String_Matching](https://www.researchgate.net/publication/2475970_Data_Compression_Using_Adaptive_Coding_and_Partial_String_Matching)

\[2\] Arithmetic Coding + Statistical Modeling = Data Compression [https://marknelson.us/posts/1991/02/01/arithmetic-coding-statistical-modeling-data-compression.html](https://marknelson.us/posts/1991/02/01/arithmetic-coding-statistical-modeling-data-compression.html)

\[3\] The zero-frequency problem: Estimating the probabilities of novel events in adaptive text compression [https://www.researchgate.net/publication/220685657_The_zero-frequency_problem_Estimating_the_probabilities_of_novel_events_in_adaptive_text_compression](https://www.researchgate.net/publication/220685657_The_zero-frequency_problem_Estimating_the_probabilities_of_novel_events_in_adaptive_text_compression)
