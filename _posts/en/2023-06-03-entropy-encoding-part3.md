---
title: "Entropy coding by a beginner for beginners - Part 3: Simple data models"
date: 2023-06-03 00:00:02 +0200
categories: [compression]
tags: [arithmetic coding, compression model]
math: true
---

## Setting test

In this part, we will start looking at how we can use the AC that was written in the previous part. Entropy coders take value that need to be encode from a model that drives compression process. The role of the model is to estimate the probability of the symbol (maybe transform data in some way before) that we are encoding and pass that probability to the entropy coder. The boundary of this interaction may be blurred, as in the case of LZ, but in our case, the separation will be quite clear. If you have watched the commits from previous part, you have already seen that they had some simple static model. Maybe it would be better to consider implementation of the model itself first, but as changes in how we use our models will be minor from the following example, I decided at first give a glance at how we will use them, so in the future, we won't be disturbed from their implementation.

```
void TestStaticAC(const file_data& InputFile)
{
    BasicACByteModel Model;

    for (size_t i = 0; i < InputFile.Size; i++)
    {
        Model.update(InputFile.Data[i]);
    }
    ...
    ByteVec CompressBuffer;
    CompressFileStatic(Model, InputFile, CompressBuffer);
    file_data OutputFile;
    ...
    DecompressFileStatic(Model, OutputFile, CompressBuffer, InputFile);
}
```

Before starting the encоding process, we first collect some statistics by calling `update()` for each byte and then perform our test.

```
void CompressFileStatic(const BasicACByteModel& Model, const file_data& InputFile,
    ByteVec& OutBuffer)
{
    ArithEncoder Encoder(OutBuffer);

    for (u32 i = 0; i < InputFile.Size; ++i)
    {
        prob SymbolProb = Model.getProb(InputFile.Data[i]);
        Encoder.encode(SymbolProb);
    }

    prob SymbolProb = Model.getEndStreamProb();
    Encoder.encode(SymbolProb);
    Encoder.flush();
}
```

Since this is a static model, for each byte, we simply get the range of CDFs corresponding to its probability, and no further manipulation with model is needed. At the end of encoding, we assume that we will not know the size of encoding source, and for this case, make a mark about the end of the stream and finish compression by calling `flush()`.

```
void DecompressFileStatic(const BasicACByteModel& Model, const file_data& OutputFile,
    ByteVec& InputBuffer, const file_data& InputFile)
{
    ArithDecoder Decoder(InputBuffer);

    u32 TotalFreqCount = Model.getCount();
    u64 ByteIndex = 0;
    for (;;)
    {
        u32 DecodedFreq = Decoder.getCurrFreq(TotalFreqCount);

        u32 DecodedSymbol;
        prob Prob = Model.getByteFromFreq(DecodedFreq, &DecodedSymbol);

        if (DecodedSymbol == BasicACByteModel::EndOfStreamSymbolIndex) break;

        Assert(DecodedSymbol <= 255);
        Assert(ByteIndex <= OutputFile.Size);
        Assert(InputFile.Data[ByteIndex] == DecodedSymbol);

        Decoder.updateDecodeRange(Prob);

        OutputFile.Data[ByteIndex++] = static_cast<u8>(DecodedSymbol);
    }
}
```
As mentioned in previous part, during decompression, we first need to obtain the encoded frequency so that we can find the CDF range of the symbol it belongs to. To do this, we save the CDF[Total] value at the beginning because it will not change. After obtain our encoded frequency `DecodedFreq` we look for the symbol it belongs to. If this is not the end of stream then we update **low** and **high** range of the AC.

## Static model

For this model we only store array of CDF for our symbols.

```
class BasicACByteModel
{
    u16 CumFreq[258]; // (0...255 = 256) + end_of_stream + total_cum_freq

    static constexpr u32 CumFreqArraySize = ArrayCount(CumFreq);
    static constexpr u32 TotalIndex = CumFreqArraySize - 1;

public:
    static constexpr u32 EndOfStreamSymbolIndex = CumFreqArraySize - 2;

    BasicACByteModel()
    {
        reset();
    }

    void reset()
    {
        MemSet<u16>(CumFreq, ArrayCount(CumFreq), 0);
    }
...
}
```

Оскільки ми не починаємо кодування доки не зберемо статистику про появу символів, ми встановлюємо наше CDF у 0. Я не використовую тут звичайний memset, тому, що, по-перше, мені потрібно було оперувати значеннями більше ніж в 1 байт, а, по-друге, в мене іноді підгорає, коли я та змінюю тип даних тощо, а змінити memset забуваю. Тому чисто для себе використовую версію де можу жорстко задати тип для *dest_ptr и value, разом із -Wconversion це іноді зберігає пару нервових клітин. Сподіваюсь на розуміння.

Since we don’t start encoding before collecting statistics of symbols appearing, we set our CDF to 0. I don’t use default memset() here because I needed to use a value bigger that 1 byte, and also because I get little annoyed when I change data type and forget to change memset() after. So, just for myself, this version allows me to strictly set data type of *dest_ptr and value, with something like -Wconverision this sometimes just save me a pair of nerve cells. Hope for your understanding.

We begin `update()` by incrementing all CDF values starting from з `Symbol + 1` since each CDF value is sum of all previous frequency value.

```
void BasicACByteModel::update(u32 Symbol)
{
    Assert((Symbol < CumFreqArraySize));

    for (u32 i = Symbol + 1; i < CumFreqArraySize; ++i)
    {
        CumFreq[i] += 1;
    }
    ...
}
```

The maximum value for our CDF[Total] is limited by `FREQ_MAX_VALUE`. This means that our next step is to check if we need to reduce our CDF values.

```
void BasicACByteModel::update(u32 Symbol)
{
    Assert((Symbol < CumFreqArraySize));
    ...
    if (CumFreq[CumFreqArraySize - 1] >= FREQ_MAX_VALUE)
    {
        for (u32 i = 1; i < CumFreqArraySize; ++i)
        {
            u16 Freq = CumFreq[i];
            Freq = (Freq + 1) / 2;

            u16 PrevFreq = CumFreq[i - 1];
            if (Freq <= PrevFreq)
            {
                Freq = PrevFreq + 1;
            }

            CumFreq[i] = Freq;
        }
    }
}
```

CDF[0] always will be 0, so we don’t touch it. After such operation can be the case when difference between CDF[i] and CDF[I - 1] will be equal to 0, while before the difference was 1. Therefore the check `Freq <= PrevFreq` is needed.

In this normalization scheme we guarantee that each symbol can be encoded, even if it didn’t appear earlier. This not cool of course, because we spend CDF range for these symbols and as a consequence, reduce the possible CDF range for symbols that really need it. Since we already store our values as CDF, we can get our range using symbol directly.

```
prob BasicACByteModel::getProb(u32 Symbol) const
{
    Assert(Symbol <= EndOfStreamSymbolIndex);

    prob Result;
    Result.lo = CumFreq[Symbol];
    Result.hi = CumFreq[Symbol + 1];
    Result.scale = CumFreq[TotalIndex];

    return Result;
}

u32 BasicACByteModel::getTotal() const
{
    return CumFreq[TotalIndex];
}

prob BasicACByteModel::getEndStreamProb() const
{
    return getProb(EndOfStreamSymbolIndex);
}
```

In order to find which symbol DecodedFreq correspond to, we need to find when the next value will be greater than the one we are looking for, because `CDF[Symbol] >= Freq < CDF[Symbol + 1]` as shown in the previous article because $Freq \in [CDF[low]; CDF[high])$. Since CDF implies that each subsequent value is at least not less than the previous one, we can check whether this is the symbol that corresponds to the passed CDF value simply by checking `Freq < CDF[Symbol + 1]`.

```
prob BasicACByteModel::getSymbolFromFreq(u32 Freq, u32* Byte) const
{
    prob Result = {};

    for (u32 i = 0; i < CumFreqArraySize; ++i)
    {
        if (Freq < CumFreq[i + 1])
        {
            *Byte = i;
            Result = getProb(i);
            break;
        }
    }

    return Result;
}
```

You may have seen from other places where someone explain how to implement AC that such model is bad. Let’s see.

| name  |   H   | file size | compr. size |  bpb  |
| :---- | :---- | :-------- | :---------- | :---- |
| book1 | 4.572 |    768771 | 437680      | 4.555 |
| geo   | 5.646 |    102400 | 72394       | 5.656 |
| obj2  | 6.26  |    246814 | 196284      | 6.362 |
| pic   | 1.21  |    513216 | 114435      | 1.784 |

Well, I think it’s obvious now why. Such a simple static model performs worse than Huffman. Tracking when `CDF[Total] >= FREQ_MAX_VALUE` is very simple way to normalize frequency, and as you have seen, it is far from optimal for use in static modeling.

## Order-0

Now as we have seen how to use AC for compression using simple static model, we can consider how to make our model adaptive, which means changing the probability of symbols during the  processing of input data. This is where the main advantage of coding using the AC method comes in. In order to unambiguously decode encоded symbols on the decoding side, the model needs to perform a symmetric (to the encoder) update of its probability. This means it adds work on both sides of the compression. When speaking about adaptive models, the general term that is used is Order-N, where N is amount of previous symbols based on which we estimate the probability for the current symbol.

It’s easy for our static model above to become Order-0, which means the estimation of probability will not directly depend on the previous symbol but on symbols that have been collected so far during processing time. For this, we need to initialize our CDFs so we can use them from the start. We just need to change the `reset()` function to set every CDF value to 1.

```
void BasicACByteModel::reset()
{
    for (u32 i = 0; i < CumFreqArraySize; ++i)
    {
        CumFreq[i] = i;
    }
}
```

Now, we don’t collect data about the symbol appearing before encoding but call `update()` after the symbol has been encoded.

```
void CompressFile(BasicACByteModel& Model, const file_data& InputFile,
    ByteVec& OutBuffer)
{
    ...
    for (u32 i = 0; i < InputFile.Size; ++i)
    {
        prob SymbolProb = Model.getProb(InputFile.Data[i]);
        Encoder.encode(SymbolProb);
        Model.update(InputFile.Data[i]);
    }
    ...
}
```

At decoding, since CDF[Total] is now changing after each symbol, we need get its value at each iteration and call `update()` at the end as we do at encoding.

```
void DecompressFile(BasicACByteModel& Model, const file_data& OutputFile,
    ByteVec& InputBuffer, const file_data& InputFile)
{
    ...
    for (;;)
    {
        u32 DecodedFreq = Decoder.getCurrFreq(Model.getTotal());
        ...
        Decoder.updateDecodeRange(Prob);
        Model.update(DecodedSymbol);

        OutputFile.Data[ByteIndex++] = DecodedSymbol;
    }
}
```

| name  |   H   | file size | compr. size |  bpb  |
| :---- | :---- | :-------- | :---------- | :---- |
| book1 | 4.572 |    768771 | 437023      | 4.548 |
| geo   | 5.646 |    102400 | 72416       | 5.658 |
| obj2  | 6.26  |    246814 | 187337      | 6.072 |
| pic   | 1.21  |    513216 | 75119       | 1.17  |

We have made our files smaller (besides `geo`)! Although difference not very impressive but changes that we made also was minimal. The fact that files got smaller with this model means that on some chunks of data, static data about symbol appearance does not show the actual symbol probability for that chunk. Therefore, static modeling is done in chunks to be able to track such changes, and not for the entire data, as I did.

## Order-1

Next, what we can try is to change our model to Order-1. The idea is that, if we take text as an example, after the letter ‘g’ in some particular text, the probability that the next letter will be ‘e’ is 80%, while for the text as a whole, the probability for ‘e’ can be only 20%. We can say that for Order-N models where N > 0, we collect data for specific context, where the context is the previous N symbols, and we do encoding for our next symbol based on data from the current context.

The API for Order-1 with how we use it will remain the same as in Order-0. The changes will only touch the implementation of this class.

```
class SimpleOrder1AC
{
    u16 Freq[257][257];
    u16 Total[257];
    u32 PrevSymbol;

    static constexpr u32 FreqArraySize = ArrayCount(Freq[0]);

public:
    static constexpr u32 EndOfStreamSymbolIndex = FreqArraySize - 1;

    SimpleOrder1AC()
    {
        reset();
    }

    void reset()
    {
        PrevSymbol = 0;
        MemSet<u16>(reinterpret_cast<u16*>(Freq), sizeof(Freq) / sizeof(u16), 1);
        MemSet<u16>(Total, sizeof(Total) / sizeof(u16), 257);
    }
}
```

This time, for the purpose of example, we will store counter for the frequency of each symbol directly, instead of using CDF values. However, now such arrays exist for each possible context. We don’t have functionality for starting from a completely empty context. For that reason, to be able to perform encoding/decoding at the beginning, we set the starting frequency for each symbol as 1. Starting value of `PrevSymbol`, we assume to be 0 because it convenient and we don’t have to add some branching in the next functions to check if `PrevSymbol` was set at all.

Like the previous time, we start with an `update()`:

```
void SimpleOrder1AC::update(u32 Symbol)
{
    u16* CtxFreq = &CumFreq[PrevSymbol][0];

    CtxFreq[Symbol]++;
    Total[PrevSymbol]++;

    if (Total[PrevSymbol] >= FREQ_MAX_VALUE)
    {
        Total[PrevSymbol] = 0;

        for (u32 i = 0; i < FreqArraySize; ++i)
        {
            u32 Freq = CtxFreq[i];
            Freq = (Freq + 1) / 2;

            CtxFreq[i] = Freq;
            Total[PrevSymbol] += Freq;
        }
    }

    PrevSymbol = Symbol;
}
```

Since we’re not working with CDFs now, we can simple increment our symbol frequency and the total sum in the current context. To get our CDF now, we need to calculate it.

```
prob SimpleOrder1AC::getProb(u32 Symbol) const
{
    Assert(Symbol <= EndOfStreamSymbolIndex);

    prob Result = {};
    const u16* CtxFreq = &Freq[PrevSymbol][0];

    for (u32 i = 0; i < Symbol; i++)
    {
        Result.lo += CtxFreq[i];
    }
    Result.hi = Result.lo + CtxFreq[Symbol];
    Result.scale = Total[PrevSymbol];

    return Result;
}
```

Earlier, we took our **low** as `CumFreq[Symbol]` and **high** as `CumFreq[Symbol + 1]`, where we basically stored the frequency of the symbol. Since the frequency is now stored directly and can be accessed by symbol index, our **low** is the sum of all previous counter up to `CtxFreq[Symbol]`. To find the high value we add `CtxFreq[Symbol]` to the already calculated **low** value. To encode the last symbol, we only need to subtract its frequency from `Total`.

```
prob SimpleOrder1AC::getEndStreamProb() const
{
    prob Result = {};
    const u16* CtxFreq = &Freq[PrevSymbol][0];

    Result.hi = Result.scale = Total[PrevSymbol];
    Result.lo = Result.hi - CtxFreq[FreqArraySize - 1];
    return Result;
}
u32 SimpleOrder1AC::getCount() const
{
    return Total[PrevSymbol];
}
```

And last is function for obtaining symbol from it encoded frequency.

```
prob SimpleOrder1AC::getSymbolFromFreq(u32 DecodeFreq, u32* Byte) const
{
    prob Result = {};
    const u16* CtxFreq = &Freq[PrevSymbol][0];

    u32 CumFreq = 0;
    u32 SymbolIndex = 0;
    for (; SymbolIndex < FreqArraySize; ++SymbolIndex)
    {
        CumFreq += CtxFreq[SymbolIndex];
        if (CumFreq > DecodeFreq) break;
    }

    Result.hi = CumFreq;
    Result.lo = Result.hi - CtxFreq[SymbolIndex];
    Result.scale = Total[PrevSymbol];
        
    *Byte = SymbolIndex;

    return Result;
}
```

We stop our search as soon as we get the **high** value that we know for sure is greater than `DecodeFreq` because `DecodeFreq < high`. We can’t stop loop as soon as we found our low range because the frequency of the next values can be 0. In this case, CDF[low] will stay the same until we loop over them. That’s why we need to be sure that this symbol has non zero counter and it fits in our range at all. Of course, minimal counter that symbol can have now is 1, but this need to know for the future.


| name  |   H   | file size | compr. size |  bpb  |
| :---- | :---- | :-------- | :---------- | :---- |
| book1 | 4.572 |    768771 | 354765      | 3.691 |
| geo   | 5.646 |    102400 | 64794       | 5.062 |
| obj2  | 6.26  |    246814 | 135828      | 4.402 |
| pic   | 1.21  |    513216 | 58668       | 0.91  |

Look better! The `pic` file benefited the most from this model, which is quite logical because it has the lowest entropy. At the same time, despite the fact that `obj2` has more entropy than `geo`, it becomes smaller both in percentage and absolute terms. This is because we can’t achieve good compression without actually knowing data that we’re trying to compress. It just so happens that data in `obj2` has better context dependency in our simple model that works with bytes, then `geo` file. To squeeze the minimum entropy from a certain type of data, we need a model that operates on the elements of that data. Hence, an ideal general-purpose compressor that is also practical, meaning it not take several days to perform compression and decompression, cannot exist (at least not at the time of writing this article). However, it is not always possible to have a separate model for each type of data. We can attempt to improve our result by increasing the Order of our model. The problem with our last implementation is that it scales very poorly. For Order-2, we would require (257 * 257 * 257) * 2 = 32 MiB, which is not too much for modern systems. However, for Order-3, we would need (257*257*257*257) * 2 = 8 GiB! Additionally, it would be really useful to have the option to not spend range on symbols that we did not encounter at all. We will solve all of this in the next parts.